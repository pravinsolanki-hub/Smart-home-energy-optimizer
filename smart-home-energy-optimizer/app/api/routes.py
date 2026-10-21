from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.models.schemas import (
    TelemetryReading,
    BenchmarkMetrics,
    ForecastResponse,
    ForecastItem,
    RecommendationResponse,
    ActionApprovalRequest,
    DeviceState,
    ComfortPreferences
)
from app.services.simulation import generate_30_day_telemetry
from app.services.forecaster import EnergyForecasterService
from app.services.optimizer import ConstrainedOptimizerService
from app.services.device_manager import DeviceManagerService
from app.integrations.aws_connector import aws_service
import sys

router = APIRouter()

# Global state instances for prototype session
data_df = generate_30_day_telemetry()
forecaster = EnergyForecasterService(data_df)
forecaster.train_and_benchmark()
optimizer = ConstrainedOptimizerService()
device_manager = DeviceManagerService()

# Cache active recommendations
_active_recommendations: Dict[str, Any] = {}

@router.get("/telemetry/live", response_model=TelemetryReading)
def get_live_telemetry():
    """Returns current real-time smart meter reading and environment telemetry."""
    latest = data_df.iloc[-1]
    reading = TelemetryReading(
        device_id="smart_meter_panel",
        indoor_temp_f=float(latest["indoor_temp"]),
        outdoor_temp_f=float(latest["outdoor_temp"]),
        humidity_pct=float(latest["humidity"]),
        active_power_kw=float(latest["kwh_demand"]),
        occupancy=bool(latest["occupancy"]),
        current_tariff_usd_kwh=float(latest["tariff_per_kwh"])
    )
    # Mirror telemetry ingestion to AWS DynamoDB service
    aws_service.ingest_telemetry_record(reading.model_dump())
    return reading

@router.get("/benchmark", response_model=BenchmarkMetrics)
def get_model_benchmark():
    """
    Returns empirical evaluation comparing the Random Forest model
    against the Naive 24-hour persistence baseline (historical persistence).
    """
    if not forecaster.benchmark_metrics:
        forecaster.train_and_benchmark()
    return forecaster.benchmark_metrics

@router.get("/forecast", response_model=ForecastResponse)
def get_24h_forecast():
    """
    Returns 24-hour ahead demand forecast, comparing baseline persistence,
    ML predicted demand, and optimized schedule with cost projections.
    """
    forecast_df = forecaster.forecast_next_24h(data_df)
    optimized_df, _ = optimizer.optimize_24h_schedule(forecast_df)

    items: List[ForecastItem] = []
    for i, row in optimized_df.iterrows():
        items.append(ForecastItem(
            hour_offset=int(i + 1),
            timestamp=str(row["timestamp"]),
            hour=int(row["hour"]),
            tariff_usd_kwh=float(row["tariff_per_kwh"]),
            is_peak_tariff=bool(row["is_peak"]),
            outdoor_temp_f=float(row["outdoor_temp"]),
            persistence_demand_kw=float(row["persistence_demand_kw"]),
            persistence_cost_usd=float(row["persistence_cost_usd"]),
            bau_demand_kw=float(row["bau_demand_kw"]),
            bau_cost_usd=float(row["bau_cost_usd"]),
            optimized_demand_kw=float(row["optimized_demand_kw"]),
            optimized_cost_usd=float(row["optimized_cost_usd"])
        ))

    total_persistence = float(optimized_df["persistence_cost_usd"].sum())
    total_bau = float(optimized_df["bau_cost_usd"].sum())
    total_opt = float(optimized_df["optimized_cost_usd"].sum())
    savings = round(max(0.0, total_bau - total_opt), 2)
    savings_pct = round((savings / total_bau) * 100.0, 1) if total_bau > 0 else 0.0

    return ForecastResponse(
        benchmark_metrics=forecaster.benchmark_metrics,
        forecast_window_hours=24,
        forecast=items,
        total_persistence_cost_usd=round(total_persistence, 2),
        total_bau_cost_usd=round(total_bau, 2),
        total_optimized_cost_usd=round(total_opt, 2),
        net_savings_usd=savings,
        savings_pct=savings_pct
    )

@router.get("/recommendations", response_model=RecommendationResponse)
def get_optimization_recommendations():
    """
    Generates explainable, actionable energy-saving recommendations
    ready for user review or Alexa voice interaction.
    """
    global _active_recommendations
    forecast_df = forecaster.forecast_next_24h(data_df)
    _, rec_response = optimizer.optimize_24h_schedule(forecast_df)
    
    # Store actions in memory for subsequent approval requests
    _active_recommendations = {act.action_id: act for act in rec_response.actions}
    return rec_response

@router.post("/actions/approve")
def approve_optimization_action(approval: ActionApprovalRequest):
    """
    Accepts approval for an action (via Dashboard or Alexa Skill)
    and updates the target device shadow state in AWS IoT Core.
    """
    global _active_recommendations
    action = _active_recommendations.get(approval.action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action ID not found or expired")

    if not approval.approved:
        action.status = "rejected"
        return {"status": "rejected", "message": f"Action {approval.action_id} was rejected by user."}

    # Apply to device shadow
    success = device_manager.apply_action(
        action_id=action.action_id,
        device_id=action.device_id,
        desired_state=action.desired_state
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Device {action.device_id} has an active manual override or could not be reached."
        )

    # Publish device shadow update to AWS IoT Core (simulation or live)
    aws_shadow_res = aws_service.update_device_shadow(
        thing_name=action.device_id,
        desired_state=action.desired_state
    )

    action.status = "approved"
    return {
        "status": "applied",
        "action_id": action.action_id,
        "device_id": action.device_id,
        "message": f"Successfully executed '{action.action_name}' on {action.device_id}.",
        "new_device_state": device_manager.get_device(action.device_id).desired_state,
        "aws_shadow_event": aws_shadow_res
    }

@router.get("/devices", response_model=List[DeviceState])
def list_devices():
    """Returns connected devices and their shadow states (reported vs. desired)."""
    return device_manager.get_all_devices()

@router.post("/devices/{device_id}/override")
def set_device_manual_override(device_id: str, payload: Dict[str, Any]):
    """Immediate manual override endpoint ensuring user comfort always takes precedence."""
    success = device_manager.set_manual_override(device_id, payload)
    if not success:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    # Update AWS shadow with override state
    aws_service.update_device_shadow(device_id, payload)

    return {
        "status": "manual_override_active",
        "device_id": device_id,
        "message": "Manual override active. Automation will not modify this device until cleared."
    }

@router.post("/devices/{device_id}/clear-override")
def clear_device_override(device_id: str):
    """Resumes automated energy optimization for the specified device."""
    success = device_manager.clear_manual_override(device_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    return {"status": "automation_restored", "device_id": device_id}

# --- Alexa+ MCP & AWS Builder Integration Routes ---

from app.alexa_mcp.server import (
    mcp_server,
    register_services,
    simulate_alexa_turn_async
)

# Register singleton service references with MCP server
register_services(forecaster, optimizer, device_manager, aws_service, data_df)

@router.get("/alexa/mcp/tools")
def get_alexa_mcp_tools():
    """Returns standard Model Context Protocol (MCP) tool schemas from the official MCPServer."""
    tools_data = []
    for tool_name, tool_obj in mcp_server._tool_manager._tools.items():
        tools_data.append({
            "name": tool_name,
            "description": tool_obj.description,
            "inputSchema": tool_obj.parameters
        })
    return {
        "mcp_spec_version": "2025-11-25",
        "server_name": mcp_server.name,
        "tools": tools_data
    }

@router.post("/alexa/chat")
async def handle_alexa_chat(body: Dict[str, str]):
    """
    Executes a conversational turn backed by runtime execution of registered MCP tools.
    """
    utterance = body.get("utterance", "")
    return await simulate_alexa_turn_async(utterance)

@router.get("/aws/status")
def get_aws_integration_status():
    """Returns status of AWS IoT Core Device Shadows and DynamoDB telemetry connector."""
    return aws_service.get_status()

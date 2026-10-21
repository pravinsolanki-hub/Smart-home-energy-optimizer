import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from mcp.server.mcpserver import MCPServer

# Initialize official Model Context Protocol (MCP) Server
mcp_server = MCPServer(
    name="smart-home-energy-optimizer",
    version="1.0.0",
    instructions=(
        "Smart Home Energy Optimizer MCP Server: provides predictive demand forecasting, "
        "cost-aware appliance scheduling against Time-of-Use tariffs, and device shadow controls."
    )
)

# Reference to application services (injected or imported)
_services_ref = {}

def register_services(forecaster, optimizer, device_manager, aws_service, data_df):
    _services_ref["forecaster"] = forecaster
    _services_ref["optimizer"] = optimizer
    _services_ref["device_manager"] = device_manager
    _services_ref["aws_service"] = aws_service
    _services_ref["data_df"] = data_df

# --- Official MCP Tool Registrations ---

@mcp_server.tool(
    name="get_energy_forecast",
    description="Retrieves the 24-hour ahead household energy demand forecast, peak pricing windows, and baseline comparison."
)
async def get_energy_forecast(hours: int = 24) -> str:
    forecaster = _services_ref.get("forecaster")
    optimizer = _services_ref.get("optimizer")
    data_df = _services_ref.get("data_df")

    if not forecaster or not optimizer:
        return json.dumps({"error": "Forecaster service not initialized"})

    forecast_df = forecaster.forecast_next_24h(data_df)
    opt_df, rec = optimizer.optimize_24h_schedule(forecast_df)

    payload = {
        "forecast_hours": hours,
        "benchmark_mae_improvement_pct": forecaster.benchmark_metrics.mae_improvement_pct,
        "persistence_reference_bill_usd": rec.persistence_projected_bill_usd,
        "bau_projected_bill_usd": rec.bau_projected_bill_usd,
        "optimized_projected_bill_usd": rec.optimized_projected_bill_usd,
        "peak_tariff_window": "16:00 - 21:00 ($0.45/kWh)",
        "off_peak_tariff": "$0.12/kWh"
    }
    return json.dumps(payload, indent=2)

@mcp_server.tool(
    name="get_energy_recommendations",
    description="Retrieves actionable, cost-saving energy optimization plans (e.g. HVAC pre-cooling, EV load shifting) with estimated dollar savings and comfort impact."
)
async def get_energy_recommendations() -> str:
    forecaster = _services_ref.get("forecaster")
    optimizer = _services_ref.get("optimizer")
    data_df = _services_ref.get("data_df")

    if not forecaster or not optimizer:
        return json.dumps({"error": "Optimizer service not initialized"})

    forecast_df = forecaster.forecast_next_24h(data_df)
    _, rec = optimizer.optimize_24h_schedule(forecast_df)

    actions_list = [
        {
            "action_id": a.action_id,
            "device": a.device_id,
            "action_name": a.action_name,
            "description": a.description,
            "rationale": a.rationale,
            "expected_savings_usd": a.expected_savings_usd,
            "comfort_impact": a.comfort_impact,
            "status": a.status.value
        }
        for a in rec.actions
    ]

    payload = {
        "bau_projected_bill_usd": rec.bau_projected_bill_usd,
        "optimized_projected_bill_usd": rec.optimized_projected_bill_usd,
        "total_savings_usd": rec.total_savings_usd,
        "total_savings_pct": rec.total_savings_pct,
        "explanation": rec.explanation_summary,
        "actions": actions_list
    }
    return json.dumps(payload, indent=2)

@mcp_server.tool(
    name="apply_energy_action",
    description="Approves and executes a specific energy-saving action on a smart appliance (thermostat or EV charger), publishing the updated shadow to AWS IoT Core."
)
async def apply_energy_action(action_id: str) -> str:
    device_manager = _services_ref.get("device_manager")
    aws_service = _services_ref.get("aws_service")
    forecaster = _services_ref.get("forecaster")
    optimizer = _services_ref.get("optimizer")
    data_df = _services_ref.get("data_df")

    forecast_df = forecaster.forecast_next_24h(data_df)
    _, rec = optimizer.optimize_24h_schedule(forecast_df)

    target_action = next((a for a in rec.actions if a.action_id == action_id or action_id == "all"), None)
    if not target_action and rec.actions:
        target_action = rec.actions[0]  # Default to primary proposed action

    if not target_action:
        return json.dumps({"status": "error", "message": f"Action {action_id} not found"})

    success = device_manager.apply_action(
        action_id=target_action.action_id,
        device_id=target_action.device_id,
        desired_state=target_action.desired_state
    )

    if not success:
        return json.dumps({"status": "rejected", "message": f"Device {target_action.device_id} has active manual override"})

    # Update AWS IoT Core Device Shadow
    shadow_res = aws_service.update_device_shadow(target_action.device_id, target_action.desired_state)

    return json.dumps({
        "status": "applied",
        "action_id": target_action.action_id,
        "device_id": target_action.device_id,
        "action_name": target_action.action_name,
        "expected_savings_usd": target_action.expected_savings_usd,
        "aws_shadow_status": shadow_res.get("status"),
        "timestamp": datetime.utcnow().isoformat()
    }, indent=2)

@mcp_server.tool(
    name="set_comfort_override",
    description="Sets an immediate manual override on a smart device, giving comfort absolute priority over energy savings."
)
async def set_comfort_override(device_id: str, setpoint_f: float) -> str:
    device_manager = _services_ref.get("device_manager")
    aws_service = _services_ref.get("aws_service")

    override_state = {"setpoint_f": setpoint_f, "mode": "cool"}
    success = device_manager.set_manual_override(device_id, override_state)
    aws_service.update_device_shadow(device_id, override_state)

    return json.dumps({
        "status": "manual_override_active",
        "device_id": device_id,
        "setpoint_f": setpoint_f,
        "message": f"Manual override active on {device_id}. Automation locked until cleared."
    }, indent=2)


# --- Streamable HTTP ASGI Application & Simulated Ambient Turn ---

def get_mcp_streamable_app():
    """Returns the official Starlette ASGI application implementing MCP Streamable HTTP."""
    return mcp_server.streamable_http_app()

async def simulate_alexa_turn_async(utterance: str) -> Dict[str, Any]:
    """
    Executes a conversational turn by dispatching directly to the registered MCP tools,
    simulating how an Alexa+ conversational agent uses MCP tools in runtime.
    """
    text = utterance.lower().strip()
    timestamp = datetime.utcnow().strftime("%I:%M %p")

    # 1. Forecast query
    if any(w in text for w in ["forecast", "demand", "usage", "prediction", "consuming"]):
        tool_call_res = await mcp_server.call_tool("get_energy_forecast", {"hours": 24})
        raw_text = tool_call_res.content[0].text
        data = json.loads(raw_text)
        speech = (
            f"Tomorrow your home is predicted to cost ${data['bau_projected_bill_usd']} under normal habits. "
            f"Peak electricity rates of 45 cents per kilowatt-hour start at 4:00 PM. "
            f"Our ML model is predicting with {data['benchmark_mae_improvement_pct']}% better accuracy than yesterday's baseline."
        )
        return {
            "user_utterance": utterance,
            "alexa_response": speech,
            "mcp_tool_invoked": {
                "tool": "get_energy_forecast",
                "arguments": {"hours": 24},
                "result": data
            },
            "timestamp": timestamp
        }

    # 2. Recommendations / Savings query
    elif any(w in text for w in ["save", "saving", "recommend", "plan", "bill", "reduce", "optimize"]):
        tool_call_res = await mcp_server.call_tool("get_energy_recommendations", {})
        raw_text = tool_call_res.content[0].text
        data = json.loads(raw_text)
        actions_summary = "; ".join([f"{a['action_name']} (${a['expected_savings_usd']} savings)" for a in data["actions"]])
        speech = (
            f"I found {len(data['actions'])} optimizations to save ${data['total_savings_usd']} today "
            f"({data['total_savings_pct']}% bill reduction). Options include: {actions_summary}. "
            f"Would you like me to apply this plan?"
        )
        return {
            "user_utterance": utterance,
            "alexa_response": speech,
            "mcp_tool_invoked": {
                "tool": "get_energy_recommendations",
                "arguments": {},
                "result": data
            },
            "timestamp": timestamp
        }

    # 3. Approve action
    elif any(w in text for w in ["approve", "apply", "yes", "confirm", "execute", "go ahead"]):
        tool_call_res = await mcp_server.call_tool("apply_energy_action", {"action_id": "all"})
        raw_text = tool_call_res.content[0].text
        data = json.loads(raw_text)
        speech = (
            f"Plan approved! I have updated your {data.get('device_id')} shadow in AWS IoT Core. "
            f"{data.get('action_name')} is now executing, saving an estimated ${data.get('expected_savings_usd')}."
        )
        return {
            "user_utterance": utterance,
            "alexa_response": speech,
            "mcp_tool_invoked": {
                "tool": "apply_energy_action",
                "arguments": {"action_id": "all"},
                "result": data
            },
            "timestamp": timestamp
        }

    # 4. Manual override
    elif any(w in text for w in ["set", "cool", "warm", "degrees", "temperature", "temp"]):
        target_temp = 69.0
        for word in text.split():
            if word.replace(".", "").isdigit():
                target_temp = float(word)
                break

        tool_call_res = await mcp_server.call_tool("set_comfort_override", {"device_id": "thermostat_main", "setpoint_f": target_temp})
        raw_text = tool_call_res.content[0].text
        data = json.loads(raw_text)
        speech = (
            f"I've adjusted your thermostat to {target_temp}°F. "
            f"Comfort priority is now active, and energy automation is temporarily paused."
        )
        return {
            "user_utterance": utterance,
            "alexa_response": speech,
            "mcp_tool_invoked": {
                "tool": "set_comfort_override",
                "arguments": {"device_id": "thermostat_main", "setpoint_f": target_temp},
                "result": data
            },
            "timestamp": timestamp
        }

    return {
        "user_utterance": utterance,
        "alexa_response": "I can help optimize your home energy. Ask: 'What is my forecast?' or 'How can I save money?'",
        "mcp_tool_invoked": None,
        "timestamp": timestamp
    }

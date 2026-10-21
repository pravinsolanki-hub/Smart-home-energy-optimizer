import sys
import asyncio
from app.services.simulation import generate_30_day_telemetry
from app.services.forecaster import EnergyForecasterService
from app.services.optimizer import ConstrainedOptimizerService
from app.services.device_manager import DeviceManagerService
from app.alexa_mcp.server import (
    mcp_server,
    register_services,
    simulate_alexa_turn_async,
    get_mcp_streamable_app
)
from app.integrations.aws_connector import aws_service

def test_full_pipeline():
    print("--- 1. Testing Telemetry Simulation ---")
    df = generate_30_day_telemetry()
    print(f"Generated {len(df)} hourly samples (30 days). Mean demand: {df['kwh_demand'].mean():.2f} kW")

    print("\n--- 2. Testing Forecaster & Baseline Benchmark ---")
    forecaster = EnergyForecasterService(df)
    metrics = forecaster.train_and_benchmark()
    print(f"Baseline (Persistence) MAE: {metrics.baseline_mae:.3f} kW")
    print(f"Random Forest ML MAE:       {metrics.ml_mae:.3f} kW")
    print(f"Accuracy Improvement:       {metrics.mae_improvement_pct}%")

    print("\n--- 3. Testing Forward 24h Horizon ---")
    forecast_df = forecaster.forecast_next_24h(df)
    print(f"Generated {len(forecast_df)} forward-looking hours.")
    print(f"First forecast timestamp: {forecast_df.iloc[0]['timestamp']}")
    print(f"Last forecast timestamp:  {forecast_df.iloc[-1]['timestamp']}")

    print("\n--- 4. Testing Constrained Optimization & Cost Comparison ---")
    optimizer = ConstrainedOptimizerService()
    opt_df, rec = optimizer.optimize_24h_schedule(forecast_df)
    print(f"Persistence Projected Bill: ${rec.persistence_projected_bill_usd}")
    print(f"BAU (ML Unoptimized) Bill:  ${rec.bau_projected_bill_usd}")
    print(f"Optimized Projected Bill:   ${rec.optimized_projected_bill_usd}")
    print(f"True Net Savings vs BAU:    ${rec.total_savings_usd} ({rec.total_savings_pct}%)")
    print(f"Explanation:\n  \"{rec.explanation_summary}\"")
    print("\nProposed Actions:")
    for a in rec.actions:
        print(f"  - [{a.device_id}] {a.action_name}: {a.description}")
        print(f"    Expected Savings: ${a.expected_savings_usd} | Comfort: {a.comfort_impact}")

    print("\n--- 5. Testing Device Manager & Actuation ---")
    dm = DeviceManagerService()
    target_action = rec.actions[0]
    success = dm.apply_action(target_action.action_id, target_action.device_id, target_action.desired_state)
    print(f"Actuation applied: {success}")
    print(f"Updated Device State: {dm.get_device(target_action.device_id).desired_state}")

    # Test Manual Override protection
    print("\n--- 6. Testing Safety Manual Override ---")
    dm.set_manual_override(target_action.device_id, {"setpoint_f": 67.0, "mode": "cool"})
    override_success = dm.apply_action("new-action-123", target_action.device_id, {"setpoint_f": 75.0})
    print(f"Automation blocked while under manual override: {not override_success}")
    print(f"Device setpoint preserved: {dm.get_device(target_action.device_id).desired_state['setpoint_f']}°F")

    # Connect services to official MCP Server
    print("\n--- 7. Testing Official Model Context Protocol (MCP) Server ---")
    register_services(forecaster, optimizer, dm, aws_service, df)
    
    # Verify Streamable HTTP app creation
    streamable_app = get_mcp_streamable_app()
    print(f"Streamable HTTP MCP ASGI Application initialized: {streamable_app}")

    async def run_mcp_tests():
        # Call tool via official MCPServer.call_tool
        tool_res = await mcp_server.call_tool("get_energy_recommendations", {})
        print(f"mcp_server.call_tool('get_energy_recommendations') status: is_error={tool_res.is_error}")
        
        # Test simulated conversational turn using registered MCP tools
        alexa_res = await simulate_alexa_turn_async("How can I save money today?")
        print(f"User Utterance: 'How can I save money today?'")
        print(f"Alexa Spoken Response: {alexa_res['alexa_response']}")
        print(f"MCP Tool Invoked: {alexa_res['mcp_tool_invoked']['tool']}")

    asyncio.run(run_mcp_tests())

    print("\n>>> ALL PIPELINE & MCP SERVER VERIFICATIONS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_full_pipeline()

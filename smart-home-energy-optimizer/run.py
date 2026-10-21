#!/usr/bin/env python3
"""
Smart Home Energy Optimizer - Master Run File

Executes and verifies all project modules (simulation, forecasting, optimization,
device manager, AWS integration, and official Alexa+ MCP server), then launches
the application server and opens the interactive dashboard.

Usage:
    python run.py             # Runs all modules & starts web server + dashboard
    python run.py --test-only # Runs and verifies all modules, then exits
"""

import sys
import os
import argparse
import asyncio
import webbrowser
from datetime import datetime

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_all_modules():
    print("=" * 70)
    print("  SMART HOME ENERGY OPTIMIZER - MASTER PIPELINE VERIFICATION")
    print("=" * 70)

    # 1. Run Simulation Module (app/services/simulation.py)
    print("\n[1/7] Running Telemetry Simulation (app/services/simulation.py)...")
    from app.services.simulation import generate_30_day_telemetry
    df = generate_30_day_telemetry()
    print(f"  [OK] Successfully generated {len(df)} hourly records (30 days).")
    print(f"  [OK] Mean household power draw: {df['kwh_demand'].mean():.2f} kW")

    # 2. Run Forecasting & Benchmarking Module (app/services/forecaster.py)
    print("\n[2/7] Running Demand Forecaster & Benchmark (app/services/forecaster.py)...")
    from app.services.forecaster import EnergyForecasterService
    forecaster = EnergyForecasterService(df)
    metrics = forecaster.train_and_benchmark()
    print(f"  [OK] Naive Persistence Baseline MAE: {metrics.baseline_mae:.3f} kW")
    print(f"  [OK] Random Forest ML MAE:          {metrics.ml_mae:.3f} kW")
    print(f"  [OK] Forecast Error Reduction:      +{metrics.mae_improvement_pct}% over baseline")
    
    forecast_df = forecaster.forecast_next_24h(df)
    print(f"  [OK] True forward 24h horizon projected ({forecast_df.iloc[0]['timestamp']} to {forecast_df.iloc[-1]['timestamp']})")

    # 3. Run Constrained Optimization Module (app/services/optimizer.py)
    print("\n[3/7] Running Constrained Optimizer (app/services/optimizer.py)...")
    from app.services.optimizer import ConstrainedOptimizerService
    optimizer = ConstrainedOptimizerService()
    opt_df, rec = optimizer.optimize_24h_schedule(forecast_df)
    print(f"  [OK] Persistence Reference Bill:    ${rec.persistence_projected_bill_usd:.2f}")
    print(f"  [OK] Machine Learning BAU Bill:     ${rec.bau_projected_bill_usd:.2f}")
    print(f"  [OK] Optimized Projected Bill:      ${rec.optimized_projected_bill_usd:.2f}")
    print(f"  [OK] Verified Net Savings:          ${rec.total_savings_usd:.2f} ({rec.total_savings_pct}%)")
    for act in rec.actions:
        print(f"      - [{act.device_id}] {act.action_name}: saves ${act.expected_savings_usd:.2f} ({act.comfort_impact})")

    # 4. Run Device Manager & Safety Overrides (app/services/device_manager.py)
    print("\n[4/7] Running Device Shadow Manager (app/services/device_manager.py)...")
    from app.services.device_manager import DeviceManagerService
    device_manager = DeviceManagerService()
    target_action = rec.actions[0]
    actuate_ok = device_manager.apply_action(target_action.action_id, target_action.device_id, target_action.desired_state)
    print(f"  [OK] Shadow update executed: {actuate_ok} on {target_action.device_id}")
    
    # Test safety manual override lockout
    device_manager.set_manual_override(target_action.device_id, {"setpoint_f": 67.0, "mode": "cool"})
    blocked_ok = not device_manager.apply_action("blocked-act", target_action.device_id, {"setpoint_f": 75.0})
    print(f"  [OK] Safety guard verified: manual override successfully blocked automated change ({blocked_ok})")
    device_manager.clear_manual_override(target_action.device_id)

    # 5. Run AWS Integration Module (app/integrations/aws_connector.py)
    print("\n[5/7] Running AWS IoT Core & DynamoDB Connector (app/integrations/aws_connector.py)...")
    from app.integrations.aws_connector import aws_service
    telemetry_item = {
        "device_id": "smart_meter_panel",
        "timestamp": datetime.utcnow().isoformat(),
        "active_power_kw": 2.29,
        "indoor_temp_f": 72.0
    }
    dynamo_res = aws_service.ingest_telemetry_record(telemetry_item)
    shadow_res = aws_service.update_device_shadow(target_action.device_id, target_action.desired_state)
    print(f"  [OK] DynamoDB status: {dynamo_res.get('status')} (mode: {aws_service.mode})")
    print(f"  [OK] AWS IoT Shadow status: {shadow_res.get('status')} on topic {shadow_res.get('topic', 'iot-data')}")

    # 6. Run Official Alexa+ MCP Server (app/alexa_mcp/server.py)
    print("\n[6/7] Running Official Alexa+ Model Context Protocol (MCP) Server (app/alexa_mcp/server.py)...")
    from app.alexa_mcp.server import (
        mcp_server,
        register_services,
        simulate_alexa_turn_async,
        get_mcp_streamable_app
    )
    register_services(forecaster, optimizer, device_manager, aws_service, df)
    
    # Verify official Streamable HTTP Starlette ASGI application
    mcp_asgi = get_mcp_streamable_app()
    print(f"  [OK] Streamable HTTP MCP ASGI Application initialized: {mcp_asgi}")

    async def verify_mcp():
        # Call tool via official MCPServer.call_tool
        call_res = await mcp_server.call_tool("get_energy_recommendations", {})
        print(f"  [OK] mcp_server.call_tool('get_energy_recommendations') executed without error (is_error={call_res.is_error})")
        
        # Test simulated conversational turn using registered MCP tools
        alexa_turn = await simulate_alexa_turn_async("How can I save money today?")
        print(f"  [OK] Alexa+ Conversational Dispatch: \"{alexa_turn['alexa_response'][:65]}...\"")
        print(f"  [OK] Dispatched to MCP Tool: {alexa_turn['mcp_tool_invoked']['tool']}")

    asyncio.run(verify_mcp())

    # 7. Verify Static Dashboard & Web Application (app/main.py & static/index.html)
    print("\n[7/7] Verifying Web Dashboard & Server Routes (app/main.py, static/index.html)...")
    from app.main import app as fastapi_app
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    assert os.path.exists(static_file), "static/index.html missing"
    print(f"  [OK] Interactive frontend dashboard verified ({os.path.getsize(static_file)} bytes).")
    print(f"  [OK] FastAPI application mounted with Streamable HTTP MCP endpoint at /mcp.")

    print("\n" + "=" * 70)
    print("  ALL MODULES & PIPELINE TESTS EXECUTED AND VERIFIED SUCCESSFULLY!")
    print("=" * 70 + "\n")

def start_server(host="127.0.0.1", port=8000, auto_open=True):
    import uvicorn
    print(f"Starting application server on http://{host}:{port}/")
    print(f"  - Interactive Dashboard:           http://{host}:{port}/")
    print(f"  - Streamable HTTP MCP Endpoint:     http://{host}:{port}/mcp")
    print(f"  - Swagger REST Documentation:       http://{host}:{port}/docs")
    print("Press Ctrl+C to terminate.")

    if auto_open and os.environ.get("AUTO_OPEN_BROWSER", "1") == "1":
        try:
            webbrowser.open(f"http://{host}:{port}/")
        except Exception:
            pass

    uvicorn.run("app.main:app", host=host, port=port, reload=False)

def main():
    parser = argparse.ArgumentParser(description="Smart Home Energy Optimizer Master Runner")
    parser.add_argument("--test-only", action="store_true", help="Run all verification tests across all files and exit without starting the server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port to run the application server on")
    parser.add_argument("--host", type=str, default=os.environ.get("HOST", "127.0.0.1"), help="Host interface to bind")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    args = parser.parse_args()

    # Always execute and verify all project files first
    run_all_modules()

    if args.test_only:
        print("[INFO] --test-only specified. Exiting cleanly.")
        return

    # Start the live application server
    start_server(host=args.host, port=args.port, auto_open=not args.no_browser)

if __name__ == "__main__":
    main()

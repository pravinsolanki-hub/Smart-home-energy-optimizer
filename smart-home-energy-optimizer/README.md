# Smart Home Energy Optimizer

An intelligent residential energy management system that forecasts electricity demand, schedules deferrable appliances against dynamic Time-of-Use (ToU) tariffs, and executes approved device adjustments via Alexa+ Model Context Protocol (MCP) and AWS IoT Core.

---

## Overview & Architecture

Most residential energy monitors only report historic consumption. This project implements a closed-loop system:

```
Telemetry Ingestion ➔ 24-Hour Forward Forecast ➔ Constrained Scheduling ➔ User Approval ➔ IoT Device Shadow Actuation
```

1. **Demand Forecasting:** A Random Forest regression model predicts total household demand for the upcoming 24 hours ($t+1 \dots t+24$) based on weather conditions, expected occupancy, and historical lag demand.
2. **Constrained Optimization:** Compares business-as-usual (BAU) consumption against an optimized schedule:
   - **HVAC Pre-Cooling & Coasting:** Runs cooling at off-peak rates ($0.25/kWh) before peak hours, allowing indoor temperatures to coast during peak pricing ($0.45/kWh) while staying strictly within the occupant's comfort envelope (68°F–76°F).
   - **EV Load Shifting:** Moves deferrable electric vehicle charging from the evening peak window (18:00–21:00) to overnight off-peak hours (00:00–04:00 at $0.12/kWh), completing at least 3 hours before morning departure.
3. **Alexa+ Model Context Protocol (MCP):** Exposes a self-hosted MCP server implementing the 2025-11-25 specification to allow Alexa+ to inspect forecasts, present rationales, and execute user-approved adjustments.
4. **AWS IoT Core Device Shadows:** Updates canonical device shadow documents (`$aws/things/{id}/shadow/update`) with desired states.
5. **Safety & Manual Override:** Occupants can manually adjust any device at any time, immediately locking out automated changes until explicitly cleared.

---

## Amazon Hackathon Track Alignment

* **Primary Track — Alexa+:**
  - Implements a self-hosted Model Context Protocol (MCP) server using the official Python MCP SDK (`mcp>=2.0`) implementing specification version 2025-11-25.
  - Mounts the official MCP Streamable HTTP ASGI application directly on `/mcp` (`mcp_server.streamable_http_app()`).
  - Registers 4 core tools: `get_energy_forecast`, `get_energy_recommendations`, `apply_energy_action`, and `set_comfort_override`.
  - Includes an interactive web dashboard simulating ambient Alexa+ conversational interactions, dispatching directly to the registered MCP tools.
* **Mini-Challenge — AWS Builder:**
  - Interacts with AWS IoT Core Device Shadows (`boto3.client('iot-data')`) and Amazon DynamoDB for telemetry storage.
  - Supports dual modes: `AWS_MODE=live` for real AWS accounts, and `AWS_MODE=simulation` for offline local verification.
* **Mini-Challenge — Open Source:**
  - Public repository with standard [MIT License](LICENSE).

---

## Empirical Benchmark & Cost Savings

The system was evaluated against 30 days (720 hours) of simulated residential telemetry, comparing our Random Forest regressor against a Naive 24-Hour Persistence Baseline ($y_t = y_{t-24}$) across a 120-hour held-out test set:

| Metric | Persistence Baseline | Random Forest Model | Delta |
| :--- | :--- | :--- | :--- |
| **Mean Absolute Error (MAE)** | 0.595 kW | 0.342 kW | **-42.49% error** |
| **Root Mean Squared Error (RMSE)** | 1.202 kW | 0.851 kW | **-29.20% error** |

### Projected 24-Hour Cost Comparison
* **Persistence Reference Cost:** $16.46
* **Business-As-Usual (BAU) Projected Bill:** $14.04
* **Optimized Projected Bill:** $10.10
* **Verified Net Daily Savings:** **$3.94 / day (28.1% bill reduction)**

---

## Quickstart

### Prerequisites
* Python 3.10+ (tested on Python 3.14)
* pip

### Installation & Execution

```bash
# 1. Clone repository
git clone <repo-url>
cd smart-home-energy-optimizer

# 2. Create and activate a virtual environment
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate
# On Linux / macOS:
# source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run test suite to verify forecasting, optimization, and MCP tools
python test_backend.py

# 5. Start the application
python run.py
```

The application will start on `http://127.0.0.1:8000/`.
* **Interactive Dashboard:** `http://127.0.0.1:8000/`
* **Swagger API Documentation:** `http://127.0.0.1:8000/docs`
* **Alexa+ MCP Tools Schema:** `http://127.0.0.1:8000/api/alexa/mcp/tools`
* **AWS Integration Status:** `http://127.0.0.1:8000/api/aws/status`

---

## Project Structure

```
smart-home-energy-optimizer/
├── run.py                       # Main application entrypoint
├── main.py                      # Alias to run.py
├── test_backend.py              # Verification test suite
├── requirements.txt             # Project dependencies (UTF-8)
├── LICENSE                      # MIT License
├── app/
│   ├── main.py                  # FastAPI application setup & routing
│   ├── models/
│   │   └── schemas.py           # Pydantic data schemas
│   ├── services/
│   │   ├── simulation.py        # 30-day telemetry simulation
│   │   ├── forecaster.py        # 24h forward forecast & baseline benchmark
│   │   ├── optimizer.py         # Constrained scheduling & savings calculation
│   │   └── device_manager.py    # Device state & manual override guards
│   ├── integrations/
│   │   └── aws_connector.py     # AWS IoT Device Shadow & DynamoDB connector
│   ├── alexa_mcp/
│   │   └── server.py            # Model Context Protocol (MCP) server for Alexa+
│   └── api/
│       └── routes.py            # REST API endpoints
└── static/
    └── index.html               # Web dashboard with Chart.js & Alexa+ simulation
```

---

## License

This project is licensed under the [MIT License](LICENSE).

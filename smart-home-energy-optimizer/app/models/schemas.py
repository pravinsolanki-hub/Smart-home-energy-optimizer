from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

class DeviceType(str, Enum):
    THERMOSTAT = "thermostat"
    EV_CHARGER = "ev_charger"
    SMART_PLUG = "smart_plug"
    HEAT_PUMP = "heat_pump"

class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"

class TelemetryReading(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    device_id: str = "main_panel"
    indoor_temp_f: float = 72.0
    outdoor_temp_f: float = 85.0
    humidity_pct: float = 45.0
    active_power_kw: float = 2.4
    occupancy: bool = True
    current_tariff_usd_kwh: float = 0.22

class BenchmarkMetrics(BaseModel):
    baseline_mae: float
    ml_mae: float
    baseline_rmse: float
    ml_rmse: float
    mae_improvement_pct: float
    eval_samples: int

class ForecastItem(BaseModel):
    hour_offset: int
    timestamp: str
    hour: int
    tariff_usd_kwh: float
    is_peak_tariff: bool
    outdoor_temp_f: float
    # Persistence baseline (yesterday at same hour)
    persistence_demand_kw: float
    persistence_cost_usd: float
    # Machine Learning Business-As-Usual (unoptimized)
    bau_demand_kw: float
    bau_cost_usd: float
    # Active Optimized Schedule (after pre-cooling & load shift)
    optimized_demand_kw: float
    optimized_cost_usd: float

class ForecastResponse(BaseModel):
    benchmark_metrics: BenchmarkMetrics
    forecast_window_hours: int
    forecast: List[ForecastItem]
    total_persistence_cost_usd: float
    total_bau_cost_usd: float
    total_optimized_cost_usd: float
    net_savings_usd: float  # Savings vs BAU
    savings_pct: float

class ComfortPreferences(BaseModel):
    min_temp_f: float = 68.0
    max_temp_f: float = 76.0
    preferred_temp_f: float = 72.0
    ev_target_kwh: float = 18.0
    ev_deadline_hour: int = 7  # 7:00 AM

class OptimizationAction(BaseModel):
    action_id: str
    device_id: str
    device_type: DeviceType
    action_name: str
    description: str
    rationale: str
    start_hour_offset: int
    duration_hours: int
    expected_savings_usd: float
    comfort_impact: str
    safety_boundary_verified: bool
    status: ActionStatus = ActionStatus.PROPOSED
    desired_state: Dict[str, Any]

class RecommendationResponse(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    persistence_projected_bill_usd: float
    bau_projected_bill_usd: float
    optimized_projected_bill_usd: float
    total_savings_usd: float
    total_savings_pct: float
    explanation_summary: str
    actions: List[OptimizationAction]

class ActionApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    override_reason: Optional[str] = None
    manual_adjustments: Optional[Dict[str, Any]] = None

class DeviceState(BaseModel):
    device_id: str
    name: str
    device_type: DeviceType
    reported_state: Dict[str, Any]
    desired_state: Dict[str, Any]
    manual_override: bool = False
    last_updated: datetime = Field(default_factory=datetime.utcnow)

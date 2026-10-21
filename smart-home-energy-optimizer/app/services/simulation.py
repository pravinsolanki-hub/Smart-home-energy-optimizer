import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple

def generate_30_day_telemetry(seed: int = 42) -> pd.DataFrame:
    """
    Generates 30 days (720 hours) of synthetic home energy telemetry,
    incorporating outdoor weather cycles, occupancy, HVAC thermodynamics,
    flexible appliance spikes, and a realistic 3-tier Time-of-Use (ToU) tariff.
    """
    np.random.seed(seed)
    n_hours = 30 * 24  # 720 hours
    start_date = datetime.now() - timedelta(days=30)
    timestamps = [start_date + timedelta(hours=i) for i in range(n_hours)]
    
    records = []
    
    for i, ts in enumerate(timestamps):
        hour = ts.hour
        day_of_week = ts.weekday()
        is_weekend = 1 if day_of_week >= 5 else 0
        
        # Diurnal outdoor temperature curve (peak at 15:00, trough at 05:00)
        daily_temp_cycle = 12 * np.sin((hour - 9) * np.pi / 12)
        base_temp = 75.0 + 3.0 * np.sin(i / 168.0 * 2 * np.pi)  # weekly weather drift
        outdoor_temp = base_temp + daily_temp_cycle + np.random.normal(0, 1.2)
        humidity = 55.0 - (outdoor_temp - 75.0) * 0.8 + np.random.normal(0, 2.5)
        
        # Occupancy logic (probabilistic)
        if is_weekend:
            occupancy_prob = 0.85 if 8 <= hour <= 22 else 0.95
        else:
            occupancy_prob = 0.30 if 9 <= hour <= 16 else 0.90
        occupancy = 1 if np.random.rand() < occupancy_prob else 0
        
        # Base household load (refrigerator, network, phantom draw, lights)
        base_load = 0.6 + (0.4 if occupancy else 0.1) + np.random.uniform(0.05, 0.15)
        
        # HVAC cooling load (thermodynamic delta against indoor baseline 72°F)
        hvac_cooling = max(0.0, (outdoor_temp - 72.0) * 0.18) if outdoor_temp > 72.0 else 0.0
        if not occupancy:
            hvac_cooling *= 0.65  # Slight setback when empty
            
        # Flexible appliances (EV charging, dishwasher, water heater)
        # In baseline behavior, EV charges as soon as plugged in (typically 18:00 - 21:00, peak hours!)
        flexible_load = 0.0
        if 18 <= hour <= 21 and np.random.rand() < 0.60:
            flexible_load += np.random.uniform(3.0, 4.5)  # EV or laundry during peak
            
        total_demand_kw = round(base_load + hvac_cooling + flexible_load, 3)
        
        # Realistic 3-Tier Time-of-Use (ToU) Tariff ($/kWh)
        # Peak: 16:00 - 21:00 ($0.45/kWh)
        # Mid-Peak: 14:00 - 16:00 ($0.25/kWh)
        # Off-Peak: All other hours ($0.12/kWh)
        if 16 <= hour < 21:
            tariff = 0.45
            is_peak = True
        elif 14 <= hour < 16:
            tariff = 0.25
            is_peak = False
        else:
            tariff = 0.12
            is_peak = False
            
        indoor_temp = 72.0 + (0.8 if total_demand_kw < 1.0 else -0.5) + np.random.normal(0, 0.2)
        
        records.append({
            "timestamp": ts.isoformat(),
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "outdoor_temp": round(outdoor_temp, 2),
            "indoor_temp": round(indoor_temp, 2),
            "humidity": round(humidity, 1),
            "occupancy": occupancy,
            "base_load_kw": round(base_load, 3),
            "hvac_load_kw": round(hvac_cooling, 3),
            "flexible_load_kw": round(flexible_load, 3),
            "kwh_demand": total_demand_kw,
            "tariff_per_kwh": tariff,
            "is_peak": is_peak
        })
        
    df = pd.DataFrame(records)
    # Lag feature: same hour 24 hours ago (Persistence Baseline)
    df["kwh_yesterday"] = df["kwh_demand"].shift(24)
    # Fill first 24 hours with local mean
    df["kwh_yesterday"] = df["kwh_yesterday"].bfill()
    
    return df

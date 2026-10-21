import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from typing import Dict, Any, List
from app.models.schemas import BenchmarkMetrics

class EnergyForecasterService:
    def __init__(self, historical_df: pd.DataFrame):
        self.df = historical_df.copy()
        self.model = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=12)
        self.features = ["hour", "day_of_week", "is_weekend", "outdoor_temp", "humidity", "occupancy", "kwh_yesterday"]
        self.target = "kwh_demand"
        self._trained = False
        self.benchmark_metrics: BenchmarkMetrics = None

    def train_and_benchmark(self) -> BenchmarkMetrics:
        """
        Splits historical data into train (past 25 days = 600 hours)
        and test (last 5 days = 120 hours).
        Evaluates Random Forest vs Naive 24h Persistence Baseline.
        """
        train_size = len(self.df) - 120
        train_df = self.df.iloc[:train_size]
        test_df = self.df.iloc[train_size:]

        X_train, y_train = train_df[self.features], train_df[self.target]
        X_test, y_test = test_df[self.features], test_df[self.target]

        # Fit ML model
        self.model.fit(X_train, y_train)
        self._trained = True

        # ML Predictions on held-out test window
        ml_preds = self.model.predict(X_test)

        # Baseline: 24h persistence (same hour previous day)
        baseline_preds = test_df["kwh_yesterday"].values

        # Evaluation
        ml_mae = mean_absolute_error(y_test, ml_preds)
        base_mae = mean_absolute_error(y_test, baseline_preds)

        ml_rmse = root_mean_squared_error(y_test, ml_preds)
        base_rmse = root_mean_squared_error(y_test, baseline_preds)

        improvement_pct = ((base_mae - ml_mae) / base_mae) * 100.0

        metrics = BenchmarkMetrics(
            baseline_mae=round(float(base_mae), 3),
            ml_mae=round(float(ml_mae), 3),
            baseline_rmse=round(float(base_rmse), 3),
            ml_rmse=round(float(ml_rmse), 3),
            mae_improvement_pct=round(float(improvement_pct), 2),
            eval_samples=len(y_test)
        )
        self.benchmark_metrics = metrics
        return metrics

    def forecast_next_24h(self, historical_slice: pd.DataFrame) -> pd.DataFrame:
        """
        Constructs a genuine 24-hour forward-looking forecast for hours t+1 to t+24.
        Generates forward timestamps, future weather forecast inputs, forward occupancy,
        and uses the true lag demand from 24h prior (t-23 to t) as lag features.
        """
        if not self._trained:
            self.train_and_benchmark()

        last_row = historical_slice.iloc[-1]
        last_ts = datetime.fromisoformat(last_row["timestamp"])

        # Construct future 24 hours (t+1 through t+24)
        future_records: List[Dict[str, Any]] = []

        # The last 24 hours of actual history are used for the 24-hour lag (kwh_yesterday)
        recent_24h_history = historical_slice.tail(24).reset_index(drop=True)

        for step in range(1, 25):
            future_ts = last_ts + timedelta(hours=step)
            hour = future_ts.hour
            day_of_week = future_ts.weekday()
            is_weekend = 1 if day_of_week >= 5 else 0

            # Projected weather forecast for tomorrow (diurnal cycle: peak at 15:00, low at 05:00)
            daily_temp_cycle = 12 * np.sin((hour - 9) * np.pi / 12)
            base_temp = 76.0  # Seasonal mean
            outdoor_temp = round(float(base_temp + daily_temp_cycle), 2)
            humidity = round(float(55.0 - (outdoor_temp - 75.0) * 0.8), 1)

            # Projected occupancy
            if is_weekend:
                occupancy = 1 if 8 <= hour <= 23 else 0
            else:
                occupancy = 0 if 9 <= hour <= 16 else 1

            # Exact lag demand: What was the recorded demand exactly 24 hours prior to this future hour?
            # For step 1 (tomorrow at T+1), 24h prior was T-23h (index 0 of recent_24h_history).
            # For step 24 (tomorrow at T+24), 24h prior was T (index 23 of recent_24h_history).
            lag_idx = step - 1
            kwh_yesterday = float(recent_24h_history.loc[lag_idx, "kwh_demand"])
            
            # Tariff schedule for future hour
            if 16 <= hour < 21:
                tariff = 0.45
                is_peak = True
            elif 14 <= hour < 16:
                tariff = 0.25
                is_peak = False
            else:
                tariff = 0.12
                is_peak = False

            # Check if recent history had EV load during peak (for realistic load shift candidate)
            historical_flexible_kw = float(recent_24h_history.loc[lag_idx].get("flexible_load_kw", 0.0))

            future_records.append({
                "timestamp": future_ts.isoformat(),
                "hour": hour,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "outdoor_temp": outdoor_temp,
                "humidity": humidity,
                "occupancy": occupancy,
                "kwh_yesterday": kwh_yesterday,
                "tariff_per_kwh": tariff,
                "is_peak": is_peak,
                "flexible_load_kw": historical_flexible_kw
            })

        forecast_df = pd.DataFrame(future_records)

        # Baseline persistence forecast: naive prediction equals same hour 24h ago
        forecast_df["baseline_persistence_demand_kw"] = forecast_df["kwh_yesterday"]

        # ML Forecast for future 24h
        X_future = forecast_df[self.features]
        forecast_df["ml_demand_kw"] = self.model.predict(X_future).round(3)

        return forecast_df

"""
PodMind — Resource Forecaster

Generates 60-minute resource consumption forecasts per pod using
Prophet (for seasonal data) with ARIMA fallback (for non-seasonal).

Produces forecast curves with confidence intervals and predicts
resource exhaustion events (OOM kills, CPU throttle) with ETA.

VULN-01 FIX: All heavy ML computations (Prophet.fit, ARIMA.fit)
are offloaded to a thread pool via asyncio.run_in_executor() to
prevent blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from typing import Any, Optional

import numpy as np
import pandas as pd

from agents.schemas import ForecastPoint, PodForecast, ResourceType

logger = logging.getLogger("podmind.agents.forecaster")

# Suppress Prophet and statsmodels verbose output
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)


class Forecaster:
    """
    Per-pod resource forecaster using Prophet with ARIMA fallback.

    Generates 60-minute ahead predictions with confidence intervals.
    Detects threshold crossings (OOM, throttle) and estimates ETA.

    All heavy computations are offloaded to a thread pool to prevent
    blocking the async event loop (VULN-01 remediation).
    """

    def __init__(
        self,
        horizon_minutes: int = 60,
        oom_threshold: float = 0.95,
        throttle_threshold: float = 0.90,
        use_prophet: bool = True,
    ):
        self._horizon = horizon_minutes
        self._oom_threshold = oom_threshold
        self._throttle_threshold = throttle_threshold
        self._use_prophet = use_prophet

    async def forecast_pod(
        self,
        pod_key: str,
        data: pd.DataFrame,
        resource_type: ResourceType,
        value_column: str,
    ) -> Optional[PodForecast]:
        """
        Generate a forecast for a single pod's resource metric.

        Args:
            pod_key: "namespace:pod" identifier.
            data: DataFrame with DatetimeIndex and value column.
            resource_type: CPU, MEMORY, STORAGE, or NETWORK.
            value_column: Column name to forecast.

        Returns:
            PodForecast with prediction points and event detection, or None.
        """
        parts = pod_key.split(":", 1)
        if len(parts) != 2:
            return None
        namespace, pod = parts

        if data.empty or value_column not in data.columns:
            return None

        series = data[value_column].dropna()
        if len(series) < 30:  # Need minimum history
            return None

        # VULN-01 FIX: Offload heavy ML fitting to thread pool
        loop = asyncio.get_running_loop()

        try:
            if self._use_prophet:
                forecast_df = await loop.run_in_executor(
                    None, self._forecast_prophet, series
                )
            else:
                forecast_df = await loop.run_in_executor(
                    None, self._forecast_arima, series
                )
        except Exception as e:
            logger.debug("Prophet failed for %s, trying ARIMA: %s", pod_key, str(e))
            try:
                forecast_df = await loop.run_in_executor(
                    None, self._forecast_arima, series
                )
            except Exception as e2:
                logger.warning("Forecasting failed for %s: %s", pod_key, str(e2))
                return None

        if forecast_df is None or forecast_df.empty:
            return None

        # Convert to forecast points
        points = []
        for idx, row in forecast_df.iterrows():
            points.append(ForecastPoint(
                timestamp=str(idx),
                predicted_value=round(float(row["yhat"]), 4),
                lower_bound=round(float(row["yhat_lower"]), 4),
                upper_bound=round(float(row["yhat_upper"]), 4),
            ))

        # Detect threshold crossings
        predicted_event = None
        eta_minutes = None
        threshold = (
            self._oom_threshold if resource_type == ResourceType.MEMORY
            else self._throttle_threshold
        )

        for i, point in enumerate(points):
            if point.predicted_value >= threshold:
                eta_minutes = (i + 1) * (self._horizon / len(points))
                if resource_type == ResourceType.MEMORY:
                    predicted_event = "OOM kill"
                elif resource_type == ResourceType.CPU:
                    predicted_event = "CPU throttle"
                else:
                    predicted_event = "Resource exhaustion"
                break

        return PodForecast(
            pod=pod,
            namespace=namespace,
            resource_type=resource_type,
            forecast_points=points,
            predicted_event=predicted_event,
            eta_minutes=round(eta_minutes, 1) if eta_minutes else None,
            confidence=0.7 if predicted_event else 0.5,
        )

    async def forecast_all(
        self,
        cpu_data: dict[str, pd.DataFrame],
        memory_data: dict[str, pd.DataFrame],
        anomalous_pods: set[str] | None = None,
    ) -> list[PodForecast]:
        """
        Forecast resources for all pods (or only anomalous pods for performance).

        Args:
            cpu_data: Normalized CPU DataFrames.
            memory_data: Normalized memory DataFrames.
            anomalous_pods: Set of "ns:pod" keys to limit forecasting to.
        """
        forecasts = []
        target_keys = anomalous_pods or set(cpu_data.keys()) | set(memory_data.keys())

        for key in target_keys:
            # Memory forecast (higher priority — OOM is critical)
            if key in memory_data:
                forecast = await self.forecast_pod(
                    key, memory_data[key], ResourceType.MEMORY, "memory_usage_ratio"
                )
                if forecast:
                    forecasts.append(forecast)

            # CPU forecast
            if key in cpu_data:
                forecast = await self.forecast_pod(
                    key, cpu_data[key], ResourceType.CPU, "cpu_usage_pct"
                )
                if forecast:
                    forecasts.append(forecast)

        logger.info("Generated %d forecasts for %d pods", len(forecasts), len(target_keys))
        return forecasts

    # -------------------------------------------------------------------------
    # Prophet Forecasting (runs in thread pool)
    # -------------------------------------------------------------------------

    def _forecast_prophet(self, series: pd.Series) -> Optional[pd.DataFrame]:
        """Generate forecast using Facebook Prophet."""
        try:
            from prophet import Prophet
        except ImportError:
            logger.warning("Prophet not installed, falling back to ARIMA")
            return self._forecast_arima(series)

        # Prophet requires DataFrame with 'ds' and 'y' columns
        prophet_df = pd.DataFrame({
            "ds": series.index,
            "y": series.values.astype(float),
        })

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=False,
            yearly_seasonality=False,
            changepoint_prior_scale=0.1,
            interval_width=0.80,
        )
        model.fit(prophet_df)

        # Create future dataframe
        freq = "5s"  # Match our collection interval
        periods = (self._horizon * 60) // 5  # Convert minutes to 5-second samples
        future = model.make_future_dataframe(periods=periods, freq=freq)

        forecast = model.predict(future)

        # Return only the forecast horizon
        forecast_only = forecast.iloc[-periods:].set_index("ds")
        return forecast_only[["yhat", "yhat_lower", "yhat_upper"]]

    # -------------------------------------------------------------------------
    # ARIMA Fallback (runs in thread pool)
    # -------------------------------------------------------------------------

    def _forecast_arima(self, series: pd.Series) -> Optional[pd.DataFrame]:
        """Generate forecast using simple ARIMA as fallback."""
        from statsmodels.tsa.arima.model import ARIMA

        values = series.values.astype(float)

        # Fit ARIMA(1,1,1) — simple but robust
        model = ARIMA(values, order=(1, 1, 1))
        fitted = model.fit()

        # Forecast
        periods = (self._horizon * 60) // 5
        forecast_result = fitted.get_forecast(steps=periods)
        predicted = forecast_result.predicted_mean
        conf_int = forecast_result.conf_int(alpha=0.20)  # 80% interval

        # Create forecast DataFrame
        last_ts = series.index[-1]
        future_index = pd.date_range(
            start=last_ts, periods=periods + 1, freq="5s"
        )[1:]

        forecast_df = pd.DataFrame({
            "yhat": predicted,
            "yhat_lower": conf_int[:, 0] if conf_int.ndim == 2 else conf_int.iloc[:, 0],
            "yhat_upper": conf_int[:, 1] if conf_int.ndim == 2 else conf_int.iloc[:, 1],
        }, index=future_index)

        return forecast_df

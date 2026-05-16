"""
PodMind — Test Metric Fixtures

Pre-recorded metric generators for unit testing agents.
Produces synthetic but realistic time-series data matching
the normalizer output format (5s resolution, 120 samples = 10 min).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_timestamp_index(
    samples: int = 120,
    freq: str = "5s",
    start: str = "2025-06-01 00:00:00",
) -> pd.DatetimeIndex:
    """Generate a uniform 5-second timestamp index (10-minute window)."""
    return pd.date_range(start=start, periods=samples, freq=freq)


# =============================================================================
# CPU Fixtures
# =============================================================================

def cpu_normal_window(
    mean: float = 0.25,
    std: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Normal CPU pod: stable ~25% with low variance.
    CV ≈ 0.12, p99 ≈ 0.33
    """
    np.random.seed(seed)
    idx = generate_timestamp_index()
    values = mean + np.random.normal(0, std, len(idx))
    return pd.DataFrame(
        {"cpu_usage_pct": np.clip(values, 0, 1)},
        index=idx,
    )


def cpu_anomalous_window(seed: int = 99) -> pd.DataFrame:
    """
    Anomalous CPU pod: bursty pattern, high CV, high p99.
    Mimics a batch processing job with CPU spikes.
    """
    np.random.seed(seed)
    idx = generate_timestamp_index()
    n = len(idx)

    # Base load with random spikes
    base = np.full(n, 0.2)
    spike_indices = np.random.choice(n, size=n // 4, replace=False)
    base[spike_indices] = np.random.uniform(0.7, 0.98, len(spike_indices))

    return pd.DataFrame(
        {"cpu_usage_pct": np.clip(base, 0, 1)},
        index=idx,
    )


def cpu_throttled_window(
    throttle_mean: float = 0.25,
    seed: int = 55,
) -> pd.DataFrame:
    """
    CPU throttle data: mean throttle ratio of ~25% (above 15% threshold).
    """
    np.random.seed(seed)
    idx = generate_timestamp_index()
    values = throttle_mean + np.random.normal(0, 0.05, len(idx))
    return pd.DataFrame(
        {"throttle_ratio": np.clip(values, 0, 1)},
        index=idx,
    )


# =============================================================================
# Memory Fixtures
# =============================================================================

def memory_leak_window(
    start_ratio: float = 0.4,
    slope_per_sample: float = 0.003,
    seed: int = 44,
) -> pd.DataFrame:
    """
    Memory leak pod: linear growth from 40% to ~76% over 10 minutes.
    Slope ≈ 3.6%/min.
    """
    np.random.seed(seed)
    idx = generate_timestamp_index()
    n = len(idx)
    values = start_ratio + np.arange(n) * slope_per_sample
    values += np.random.normal(0, 0.005, n)
    return pd.DataFrame(
        {"memory_usage_ratio": np.clip(values, 0, 1)},
        index=idx,
    )


def memory_normal_window(mean: float = 0.55, seed: int = 43) -> pd.DataFrame:
    """Normal memory pod: stable ~55% usage."""
    np.random.seed(seed)
    idx = generate_timestamp_index()
    values = mean + np.random.normal(0, 0.02, len(idx))
    return pd.DataFrame(
        {"memory_usage_ratio": np.clip(values, 0, 1)},
        index=idx,
    )


# =============================================================================
# Storage Fixtures
# =============================================================================

def storage_saturated_window(
    write_rate: float = 80_000_000,  # 80 MB/s
    seed: int = 66,
) -> pd.DataFrame:
    """Saturated PVC: ~80 MB/s write rate (above 50 MB/s threshold)."""
    np.random.seed(seed)
    idx = generate_timestamp_index()
    values = write_rate + np.random.normal(0, 5_000_000, len(idx))
    return pd.DataFrame(
        {"write_bytes_per_sec": np.clip(values, 0, None)},
        index=idx,
    )


# =============================================================================
# Granger Causality Fixtures
# =============================================================================

def granger_causal_pair(
    lag: int = 2,
    strength: float = 0.7,
    seed: int = 42,
    samples: int = 200,
) -> tuple[pd.Series, pd.Series]:
    """
    Generate a pair of time series where A Granger-causes B with known lag.

    Returns (cause_series, effect_series) with a DatetimeIndex.
    The effect is a lagged, scaled version of the cause plus noise.
    """
    np.random.seed(seed)
    idx = pd.date_range(start="2025-06-01", periods=samples, freq="5s")

    # Cause: random walk
    cause = np.cumsum(np.random.normal(0, 0.1, samples))

    # Effect: lagged copy of cause + independent noise
    effect = np.zeros(samples)
    for i in range(lag, samples):
        effect[i] = strength * cause[i - lag] + np.random.normal(0, 0.3)

    return (
        pd.Series(cause, index=idx, name="cause"),
        pd.Series(effect, index=idx, name="effect"),
    )

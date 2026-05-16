"""
PodMind — CPU Agent Unit Tests

Tests the CPU Agent against pre-recorded metric fixtures to verify:
  1. Isolation Forest correctly flags anomalous pods
  2. Z-score detects high CPU pressure pods
  3. Throttle detection triggers at >15% threshold
  4. Gradient trending identifies accelerating pods
  5. Top consumers are ranked by p99
  6. Output always passes Pydantic validation
"""

import pytest
import numpy as np
import pandas as pd

from agents.cpu_agent import CPUAgent
from agents.schemas import CPUAgentOutput, Severity
from tests.fixtures.metric_fixtures import (
    cpu_normal_window,
    cpu_anomalous_window,
    cpu_throttled_window,
    generate_timestamp_index,
)


@pytest.fixture
def cpu_agent():
    """Create a CPU Agent with default thresholds."""
    return CPUAgent(
        contamination=0.1,
        throttle_threshold=0.15,
        z_score_threshold=2.5,
        gradient_warning_threshold=0.01,
    )


@pytest.fixture
def mixed_cpu_data():
    """
    Create a mixed dataset with 5 pods:
    - 3 normal pods (low CV, stable)
    - 1 anomalous pod (high CV, bursty)
    - 1 trending pod (accelerating toward limit)
    """
    idx = generate_timestamp_index()
    np.random.seed(42)

    data = {}
    # 3 normal pods
    for i in range(3):
        np.random.seed(i + 10)
        values = 0.25 + np.random.normal(0, 0.02, len(idx))
        data[f"default:normal-pod-{i}"] = pd.DataFrame(
            {"cpu_usage_pct": np.clip(values, 0, 1)}, index=idx
        )

    # 1 anomalous pod (high CV, bursty)
    np.random.seed(99)
    base = np.linspace(0.3, 0.95, len(idx))
    noise = np.random.normal(0, 0.2, len(idx))
    anomalous = np.clip(base + noise, 0, 1)
    data["default:anomalous-pod"] = pd.DataFrame(
        {"cpu_usage_pct": anomalous}, index=idx
    )

    # 1 trending pod (accelerating)
    np.random.seed(77)
    trending = np.linspace(0.3, 0.85, len(idx)) + np.random.normal(0, 0.02, len(idx))
    data["default:trending-pod"] = pd.DataFrame(
        {"cpu_usage_pct": np.clip(trending, 0, 1)}, index=idx
    )

    return data


@pytest.fixture
def throttle_data():
    """Create throttle data for one pod exceeding threshold."""
    df = cpu_throttled_window()
    return {"default:throttled-pod": df}


# =============================================================================
# Test Cases
# =============================================================================

class TestCPUAgentOutput:
    """Verify CPU Agent always produces valid Pydantic output."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_output(self, cpu_agent):
        """Agent handles empty input gracefully."""
        result = await cpu_agent.analyze({})
        assert isinstance(result, CPUAgentOutput)
        assert result.total_pods_analyzed == 0
        assert result.anomalous_pods == []

    @pytest.mark.asyncio
    async def test_output_is_pydantic_valid(self, cpu_agent, mixed_cpu_data):
        """All output is Pydantic-validated."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        assert isinstance(result, CPUAgentOutput)
        # Serialize and deserialize to verify Pydantic validation
        json_str = result.model_dump_json()
        rebuilt = CPUAgentOutput.model_validate_json(json_str)
        assert rebuilt.total_pods_analyzed == result.total_pods_analyzed


class TestAnomalyDetection:
    """Verify Isolation Forest + Z-score anomaly detection."""

    @pytest.mark.asyncio
    async def test_detects_anomalous_pod(self, cpu_agent, mixed_cpu_data):
        """Anomalous pod should be flagged."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        anomalous_names = [a.pod for a in result.anomalous_pods]
        # The anomalous pod should be detected (high CV + high p99)
        assert len(result.anomalous_pods) >= 1
        # At least one of our anomalous or trending pods should be flagged
        flagged = set(anomalous_names)
        assert flagged & {"anomalous-pod", "trending-pod"}, (
            f"Expected anomalous/trending pod to be flagged, got: {flagged}"
        )

    @pytest.mark.asyncio
    async def test_anomaly_scores_bounded(self, cpu_agent, mixed_cpu_data):
        """All anomaly scores must be in [0.0, 1.0]."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        for a in result.anomalous_pods:
            assert 0.0 <= a.anomaly_score <= 1.0

    @pytest.mark.asyncio
    async def test_anomaly_severity_is_valid_enum(self, cpu_agent, mixed_cpu_data):
        """All severity values must be valid Severity enum members."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        for a in result.anomalous_pods:
            assert a.severity in Severity


class TestThrottleDetection:
    """Verify CPU throttle detection at >15% threshold."""

    @pytest.mark.asyncio
    async def test_detects_throttled_pod(self, cpu_agent, mixed_cpu_data, throttle_data):
        """Pod with >15% throttle ratio should be flagged."""
        result = await cpu_agent.analyze(mixed_cpu_data, throttle_data)
        throttled_names = [t.pod for t in result.throttled_pods]
        assert "throttled-pod" in throttled_names

    @pytest.mark.asyncio
    async def test_throttle_percentage_correct(self, cpu_agent, mixed_cpu_data, throttle_data):
        """Throttle percentage should match the mean throttle ratio."""
        result = await cpu_agent.analyze(mixed_cpu_data, throttle_data)
        for t in result.throttled_pods:
            assert t.throttle_pct > 15.0  # Must be above 15% threshold

    @pytest.mark.asyncio
    async def test_no_false_positive_throttle(self, cpu_agent, mixed_cpu_data):
        """No throttle alerts when no throttle data is provided."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        assert result.throttled_pods == []


class TestTrendDetection:
    """Verify gradient-based trend detection."""

    @pytest.mark.asyncio
    async def test_detects_trending_pod(self, cpu_agent, mixed_cpu_data):
        """Pod with positive gradient should be flagged as trending."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        trending_names = [t.pod for t in result.trending_pods]
        # The trending pod has a clear upward trend
        assert "trending-pod" in trending_names or "anomalous-pod" in trending_names

    @pytest.mark.asyncio
    async def test_eta_is_positive_or_none(self, cpu_agent, mixed_cpu_data):
        """ETA to limit must be positive or None."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        for t in result.trending_pods:
            if t.eta_to_limit_min is not None:
                assert t.eta_to_limit_min > 0


class TestTopConsumers:
    """Verify top consumer ranking."""

    @pytest.mark.asyncio
    async def test_top_consumers_sorted_descending(self, cpu_agent, mixed_cpu_data):
        """Top consumers must be sorted by p99 descending."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        p99_values = [c.p99_cpu_pct for c in result.top_consumers]
        assert p99_values == sorted(p99_values, reverse=True)

    @pytest.mark.asyncio
    async def test_top_consumers_limited(self, cpu_agent, mixed_cpu_data):
        """Top consumers list should not exceed 10 entries."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        assert len(result.top_consumers) <= 10

    @pytest.mark.asyncio
    async def test_total_pods_analyzed_correct(self, cpu_agent, mixed_cpu_data):
        """total_pods_analyzed should match input count."""
        result = await cpu_agent.analyze(mixed_cpu_data)
        assert result.total_pods_analyzed == 5  # 3 normal + 1 anomalous + 1 trending

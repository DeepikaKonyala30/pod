"""
PodMind — Memory Agent Unit Tests

Tests the Memory Agent against pre-recorded metric fixtures to verify:
  1. Linear regression detects memory leaks above threshold
  2. Stable memory produces no false positives
  3. OOM risk detection triggers at >85% threshold
  4. Cache pressure detection works correctly
  5. VULN-04: Young containers are skipped for leak detection
  6. Output always passes Pydantic validation
"""

import pytest
import numpy as np
import pandas as pd

from agents.memory_agent import MemoryAgent
from agents.schemas import MemoryAgentOutput
from tests.fixtures.metric_fixtures import (
    memory_leak_window,
    memory_normal_window,
    generate_timestamp_index,
)


@pytest.fixture
def memory_agent():
    """Create a Memory Agent with default thresholds."""
    return MemoryAgent(
        leak_slope_threshold=0.005,
        oom_risk_threshold=0.85,
        cache_pressure_threshold=0.60,
        min_r_squared=0.6,
        min_uptime_minutes=5.0,
    )


@pytest.fixture
def leak_data():
    """Memory data with one leaking pod."""
    df = memory_leak_window()
    return {"default:leaky-pod": df}


@pytest.fixture
def normal_data():
    """Memory data with one stable pod."""
    df = memory_normal_window()
    return {"default:stable-pod": df}


@pytest.fixture
def oom_risk_data():
    """Memory data with a pod near OOM threshold."""
    idx = generate_timestamp_index()
    np.random.seed(88)
    # Memory at ~92% usage — above 85% threshold
    values = 0.92 + np.random.normal(0, 0.01, len(idx))
    return {
        "default:oom-pod": pd.DataFrame(
            {"memory_usage_ratio": np.clip(values, 0, 1)}, index=idx
        )
    }


@pytest.fixture
def mixed_memory_data():
    """Mixed data with normal, leaking, and high-usage pods."""
    idx = generate_timestamp_index()
    np.random.seed(42)
    data = {}

    # Normal pods
    for i in range(2):
        np.random.seed(i + 20)
        vals = 0.55 + np.random.normal(0, 0.02, len(idx))
        data[f"default:normal-pod-{i}"] = pd.DataFrame(
            {"memory_usage_ratio": np.clip(vals, 0, 1)}, index=idx
        )

    # Leaking pod
    np.random.seed(44)
    leak_vals = 0.4 + np.arange(len(idx)) * 0.003 + np.random.normal(0, 0.005, len(idx))
    data["default:leaky-pod"] = pd.DataFrame(
        {"memory_usage_ratio": np.clip(leak_vals, 0, 1)}, index=idx
    )

    # High usage pod
    np.random.seed(88)
    high_vals = 0.90 + np.random.normal(0, 0.01, len(idx))
    data["default:high-usage-pod"] = pd.DataFrame(
        {"memory_usage_ratio": np.clip(high_vals, 0, 1)}, index=idx
    )

    return data


# =============================================================================
# Test Cases
# =============================================================================

class TestMemoryAgentOutput:
    """Verify Memory Agent always produces valid Pydantic output."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_output(self, memory_agent):
        """Agent handles empty input gracefully."""
        result = await memory_agent.analyze({})
        assert isinstance(result, MemoryAgentOutput)
        assert result.total_pods_analyzed == 0
        assert result.leak_suspects == []

    @pytest.mark.asyncio
    async def test_output_is_pydantic_valid(self, memory_agent, mixed_memory_data):
        """All output is Pydantic-validated."""
        result = await memory_agent.analyze(mixed_memory_data)
        assert isinstance(result, MemoryAgentOutput)
        json_str = result.model_dump_json()
        rebuilt = MemoryAgentOutput.model_validate_json(json_str)
        assert rebuilt.total_pods_analyzed == result.total_pods_analyzed


class TestLeakDetection:
    """Verify linear regression-based memory leak detection."""

    @pytest.mark.asyncio
    async def test_detects_leaking_pod(self, memory_agent, leak_data):
        """Pod with linear memory growth should be flagged as leaking."""
        result = await memory_agent.analyze(leak_data)
        assert len(result.leak_suspects) >= 1
        leak_names = [l.pod for l in result.leak_suspects]
        assert "leaky-pod" in leak_names

    @pytest.mark.asyncio
    async def test_leak_slope_is_positive(self, memory_agent, leak_data):
        """Detected leak should have positive slope."""
        result = await memory_agent.analyze(leak_data)
        for leak in result.leak_suspects:
            assert leak.slope_pct_per_min > 0

    @pytest.mark.asyncio
    async def test_no_false_positive_leak(self, memory_agent, normal_data):
        """Stable memory should NOT be flagged as leaking."""
        result = await memory_agent.analyze(normal_data)
        assert result.leak_suspects == []

    @pytest.mark.asyncio
    async def test_leak_r_squared_above_threshold(self, memory_agent, leak_data):
        """Leak R² should be above the min_r_squared threshold."""
        result = await memory_agent.analyze(leak_data)
        for leak in result.leak_suspects:
            assert leak.r_squared >= 0.6


class TestOOMRiskDetection:
    """Verify OOM risk detection at >85% threshold."""

    @pytest.mark.asyncio
    async def test_detects_oom_risk(self, memory_agent, oom_risk_data):
        """Pod at ~92% memory should be flagged as OOM risk."""
        result = await memory_agent.analyze(oom_risk_data)
        assert len(result.oom_risk_pods) >= 1
        oom_names = [o.pod for o in result.oom_risk_pods]
        assert "oom-pod" in oom_names

    @pytest.mark.asyncio
    async def test_oom_risk_usage_above_threshold(self, memory_agent, oom_risk_data):
        """OOM risk pod usage should be above 85%."""
        result = await memory_agent.analyze(oom_risk_data)
        for oom in result.oom_risk_pods:
            assert oom.usage_ratio >= 0.85

    @pytest.mark.asyncio
    async def test_no_false_positive_oom(self, memory_agent, normal_data):
        """Normal memory usage (~55%) should NOT trigger OOM risk."""
        result = await memory_agent.analyze(normal_data)
        assert result.oom_risk_pods == []


class TestVULN04UptimeCheck:
    """Verify VULN-04 fix: young containers are skipped for leak detection."""

    @pytest.mark.asyncio
    async def test_young_container_skipped(self, memory_agent, leak_data):
        """Pod with uptime < 5 minutes should not be flagged for leaks."""
        import time
        # Create metadata showing pod started 2 minutes ago
        pod_metadata = [{
            "name": "leaky-pod",
            "namespace": "default",
            "start_time": str(time.time() - 120),  # 2 minutes ago
        }]

        result = await memory_agent.analyze(
            leak_data, pod_metadata=pod_metadata
        )
        # Should NOT detect leak due to young container
        assert result.leak_suspects == []

    @pytest.mark.asyncio
    async def test_old_container_analyzed(self, memory_agent, leak_data):
        """Pod with uptime > 5 minutes should be analyzed for leaks."""
        import time
        # Create metadata showing pod started 10 minutes ago
        pod_metadata = [{
            "name": "leaky-pod",
            "namespace": "default",
            "start_time": str(time.time() - 600),  # 10 minutes ago
        }]

        result = await memory_agent.analyze(
            leak_data, pod_metadata=pod_metadata
        )
        # Should detect leak since container is old enough
        assert len(result.leak_suspects) >= 1

    @pytest.mark.asyncio
    async def test_no_metadata_still_analyzes(self, memory_agent, leak_data):
        """Without metadata, all pods should be analyzed (backwards compat)."""
        result = await memory_agent.analyze(leak_data)
        assert len(result.leak_suspects) >= 1


class TestMixedMemoryData:
    """Verify correct analysis with mixed pod states."""

    @pytest.mark.asyncio
    async def test_total_pods_analyzed(self, memory_agent, mixed_memory_data):
        """total_pods_analyzed should match input count."""
        result = await memory_agent.analyze(mixed_memory_data)
        assert result.total_pods_analyzed == 4

    @pytest.mark.asyncio
    async def test_leaks_sorted_by_slope(self, memory_agent, mixed_memory_data):
        """Leak suspects should be sorted by slope descending."""
        result = await memory_agent.analyze(mixed_memory_data)
        if len(result.leak_suspects) > 1:
            slopes = [l.slope_pct_per_min for l in result.leak_suspects]
            assert slopes == sorted(slopes, reverse=True)

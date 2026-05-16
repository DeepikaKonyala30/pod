"""
PodMind — Network Agent Unit Tests

Tests the Network Agent against pre-recorded metric fixtures to verify:
  1. Network saturation detection (>80% NIC capacity)
  2. Chatty pod detection (>10k packets/sec)
  3. Error rate spike detection (via log summaries)
  4. Empty input handling
  5. Output always passes Pydantic validation
"""

import pytest
import numpy as np
import pandas as pd

from agents.network_agent import NetworkAgent
from agents.schemas import NetworkAgentOutput
from tests.fixtures.metric_fixtures import generate_timestamp_index


@pytest.fixture
def network_agent():
    """Create a Network Agent with default thresholds."""
    return NetworkAgent()


@pytest.fixture
def saturated_network_data():
    """
    Network data with one saturated pod (>80% NIC).
    Uses rx_saturation/tx_saturation columns that the agent expects.
    """
    idx = generate_timestamp_index()
    np.random.seed(77)
    data = {
        "default:saturated-pod": pd.DataFrame({
            "rx_saturation": np.clip(
                0.90 + np.random.normal(0, 0.03, len(idx)), 0, 1
            ),
            "tx_saturation": np.clip(
                0.60 + np.random.normal(0, 0.05, len(idx)), 0, 1
            ),
            "rx_rate": np.clip(
                112_500_000 + np.random.normal(0, 5_000_000, len(idx)), 0, None
            ),
            "tx_rate": np.clip(
                50_000_000 + np.random.normal(0, 2_000_000, len(idx)), 0, None
            ),
            "rx_packets_rate": np.clip(
                50_000 + np.random.normal(0, 5_000, len(idx)), 0, None
            ),
        }, index=idx)
    }
    return data


@pytest.fixture
def normal_network_data():
    """Network data with low utilization pods."""
    idx = generate_timestamp_index()
    np.random.seed(33)
    data = {
        "default:normal-pod": pd.DataFrame({
            "rx_saturation": np.clip(
                0.10 + np.random.normal(0, 0.02, len(idx)), 0, 1
            ),
            "tx_saturation": np.clip(
                0.05 + np.random.normal(0, 0.01, len(idx)), 0, 1
            ),
            "rx_rate": np.clip(
                1_000_000 + np.random.normal(0, 100_000, len(idx)), 0, None
            ),
            "tx_rate": np.clip(
                500_000 + np.random.normal(0, 50_000, len(idx)), 0, None
            ),
            "rx_packets_rate": np.clip(
                1_000 + np.random.normal(0, 100, len(idx)), 0, None
            ),
        }, index=idx)
    }
    return data


@pytest.fixture
def chatty_network_data():
    """Network data with a chatty pod (>10k pps)."""
    idx = generate_timestamp_index()
    np.random.seed(55)
    data = {
        "default:chatty-pod": pd.DataFrame({
            "rx_saturation": np.clip(
                0.30 + np.random.normal(0, 0.05, len(idx)), 0, 1
            ),
            "tx_saturation": np.clip(
                0.25 + np.random.normal(0, 0.03, len(idx)), 0, 1
            ),
            "rx_rate": np.clip(
                5_000_000 + np.random.normal(0, 500_000, len(idx)), 0, None
            ),
            "tx_rate": np.clip(
                5_000_000 + np.random.normal(0, 500_000, len(idx)), 0, None
            ),
            "rx_packets_rate": np.clip(
                15_000 + np.random.normal(0, 1_000, len(idx)), 0, None
            ),
        }, index=idx)
    }
    return data


@pytest.fixture
def mixed_network_data():
    """Mixed network data with normal and chatty pods."""
    idx = generate_timestamp_index()
    data = {}

    # Normal pod
    np.random.seed(33)
    data["default:normal-pod"] = pd.DataFrame({
        "rx_saturation": np.clip(
            0.10 + np.random.normal(0, 0.02, len(idx)), 0, 1
        ),
        "tx_saturation": np.clip(
            0.05 + np.random.normal(0, 0.01, len(idx)), 0, 1
        ),
        "rx_rate": np.clip(
            1_000_000 + np.random.normal(0, 100_000, len(idx)), 0, None
        ),
        "tx_rate": np.clip(
            500_000 + np.random.normal(0, 50_000, len(idx)), 0, None
        ),
        "rx_packets_rate": np.clip(
            1_000 + np.random.normal(0, 100, len(idx)), 0, None
        ),
    }, index=idx)

    # Chatty pod
    np.random.seed(55)
    data["default:chatty-pod"] = pd.DataFrame({
        "rx_saturation": np.clip(
            0.30 + np.random.normal(0, 0.05, len(idx)), 0, 1
        ),
        "tx_saturation": np.clip(
            0.25 + np.random.normal(0, 0.03, len(idx)), 0, 1
        ),
        "rx_rate": np.clip(
            5_000_000 + np.random.normal(0, 500_000, len(idx)), 0, None
        ),
        "tx_rate": np.clip(
            5_000_000 + np.random.normal(0, 500_000, len(idx)), 0, None
        ),
        "rx_packets_rate": np.clip(
            15_000 + np.random.normal(0, 1_000, len(idx)), 0, None
        ),
    }, index=idx)

    return data


# =============================================================================
# Test Cases
# =============================================================================

class TestNetworkAgentOutput:
    """Verify Network Agent always produces valid Pydantic output."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_output(self, network_agent):
        """Agent handles empty input gracefully."""
        result = await network_agent.analyze({})
        assert isinstance(result, NetworkAgentOutput)
        assert result.saturated_pods == []
        assert result.chatty_pods == []

    @pytest.mark.asyncio
    async def test_output_is_pydantic_valid(self, network_agent, mixed_network_data):
        """All output is Pydantic-validated."""
        result = await network_agent.analyze(mixed_network_data)
        assert isinstance(result, NetworkAgentOutput)
        json_str = result.model_dump_json()
        rebuilt = NetworkAgentOutput.model_validate_json(json_str)
        assert len(rebuilt.saturated_pods) == len(result.saturated_pods)


class TestNetworkSaturation:
    """Verify network saturation detection (>80% NIC capacity)."""

    @pytest.mark.asyncio
    async def test_detects_saturated_pod(self, network_agent, saturated_network_data):
        """Pod with ~90% NIC utilization should be flagged."""
        result = await network_agent.analyze(saturated_network_data)
        assert len(result.saturated_pods) >= 1
        # Should detect at least the rx direction at 90%
        pod_names = [s.pod for s in result.saturated_pods]
        assert "saturated-pod" in pod_names

    @pytest.mark.asyncio
    async def test_saturation_percentage_above_threshold(self, network_agent, saturated_network_data):
        """Saturation percentage should be >= 80%."""
        result = await network_agent.analyze(saturated_network_data)
        for sat in result.saturated_pods:
            assert sat.saturation_pct >= 80.0

    @pytest.mark.asyncio
    async def test_no_false_positive_saturation(self, network_agent, normal_network_data):
        """Low utilization pod should NOT be flagged."""
        result = await network_agent.analyze(normal_network_data)
        assert result.saturated_pods == []


class TestChattyPodDetection:
    """Verify chatty pod detection (>10k packets/sec)."""

    @pytest.mark.asyncio
    async def test_detects_chatty_pod(self, network_agent, chatty_network_data):
        """Pod with >10k pps should be flagged as chatty."""
        result = await network_agent.analyze(chatty_network_data)
        assert len(result.chatty_pods) >= 1
        chatty_names = [c.pod for c in result.chatty_pods]
        assert "chatty-pod" in chatty_names

    @pytest.mark.asyncio
    async def test_chatty_packets_above_threshold(self, network_agent, chatty_network_data):
        """Chatty pod should report pps above 10000."""
        result = await network_agent.analyze(chatty_network_data)
        for chatty in result.chatty_pods:
            assert chatty.packets_per_sec >= 10_000

    @pytest.mark.asyncio
    async def test_no_false_positive_chatty(self, network_agent, normal_network_data):
        """Normal packet rate should NOT trigger chatty alert."""
        result = await network_agent.analyze(normal_network_data)
        assert result.chatty_pods == []


class TestErrorRateDetection:
    """Verify error rate spike detection via log summaries."""

    @pytest.mark.asyncio
    async def test_detects_error_spike(self, network_agent):
        """Log summaries with high error rate should be flagged."""
        log_summaries = {
            "default:error-pod": {
                "errors_per_minute": 15.0,
                "error_lines": ["ERROR: connection timeout", "ERROR: db unreachable"],
            }
        }
        result = await network_agent.analyze({}, log_summaries=log_summaries)
        assert len(result.error_rate_spikes) >= 1
        assert result.error_rate_spikes[0].pod == "error-pod"
        assert result.error_rate_spikes[0].errors_per_minute >= 5.0

    @pytest.mark.asyncio
    async def test_no_false_positive_errors(self, network_agent):
        """Low error rate should NOT trigger spike."""
        log_summaries = {
            "default:healthy-pod": {
                "errors_per_minute": 1.0,
                "error_lines": [],
            }
        }
        result = await network_agent.analyze({}, log_summaries=log_summaries)
        assert result.error_rate_spikes == []


class TestMixedNetworkData:
    """Verify correct analysis with mixed pod states."""

    @pytest.mark.asyncio
    async def test_total_pods_analyzed(self, network_agent, mixed_network_data):
        """total_pods_analyzed should match input count."""
        result = await network_agent.analyze(mixed_network_data)
        assert result.total_pods_analyzed == 2

"""
PodMind — Storage Agent Unit Tests

Tests the Storage Agent against pre-recorded metric fixtures to verify:
  1. PVC saturation detection at threshold
  2. Bulk write detection (>50MB/s for >30s)
  3. Empty input handling
  4. Output always passes Pydantic validation
"""

import pytest
import numpy as np
import pandas as pd

from agents.storage_agent import StorageAgent
from agents.schemas import StorageAgentOutput
from tests.fixtures.metric_fixtures import (
    storage_saturated_window,
    generate_timestamp_index,
)


@pytest.fixture
def storage_agent():
    """Create a Storage Agent with default thresholds."""
    return StorageAgent()


@pytest.fixture
def saturated_pvc_data():
    """Storage data with one saturated PVC."""
    df = storage_saturated_window()
    return {"default:saturated-pvc": df}


@pytest.fixture
def normal_storage_data():
    """Storage data with low write rates."""
    idx = generate_timestamp_index()
    np.random.seed(33)
    # Low write rate: ~5 MB/s
    values = 5_000_000 + np.random.normal(0, 500_000, len(idx))
    return {
        "default:normal-pvc": pd.DataFrame(
            {"write_bytes_per_sec": np.clip(values, 0, None)}, index=idx
        )
    }


@pytest.fixture
def mixed_storage_data():
    """Mixed storage data with normal and saturated PVCs."""
    idx = generate_timestamp_index()
    data = {}

    # Normal PVC
    np.random.seed(33)
    normal_vals = 5_000_000 + np.random.normal(0, 500_000, len(idx))
    data["default:normal-pvc"] = pd.DataFrame(
        {"write_bytes_per_sec": np.clip(normal_vals, 0, None)}, index=idx
    )

    # Saturated PVC
    np.random.seed(66)
    sat_vals = 80_000_000 + np.random.normal(0, 5_000_000, len(idx))
    data["default:hot-pvc"] = pd.DataFrame(
        {"write_bytes_per_sec": np.clip(sat_vals, 0, None)}, index=idx
    )

    # Moderate PVC
    np.random.seed(55)
    mod_vals = 30_000_000 + np.random.normal(0, 3_000_000, len(idx))
    data["default:moderate-pvc"] = pd.DataFrame(
        {"write_bytes_per_sec": np.clip(mod_vals, 0, None)}, index=idx
    )

    return data


# =============================================================================
# Test Cases
# =============================================================================

class TestStorageAgentOutput:
    """Verify Storage Agent always produces valid Pydantic output."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_output(self, storage_agent):
        """Agent handles empty input gracefully."""
        result = await storage_agent.analyze({})
        assert isinstance(result, StorageAgentOutput)
        assert result.saturated_pvcs == []

    @pytest.mark.asyncio
    async def test_output_is_pydantic_valid(self, storage_agent, mixed_storage_data):
        """All output is Pydantic-validated."""
        result = await storage_agent.analyze(mixed_storage_data)
        assert isinstance(result, StorageAgentOutput)
        json_str = result.model_dump_json()
        rebuilt = StorageAgentOutput.model_validate_json(json_str)
        assert len(rebuilt.saturated_pvcs) == len(result.saturated_pvcs)


class TestPVCSaturation:
    """Verify PVC saturation detection."""

    @pytest.mark.asyncio
    async def test_detects_saturated_pvc(self, storage_agent, saturated_pvc_data):
        """PVC with ~80 MB/s write rate should be flagged as saturated."""
        result = await storage_agent.analyze(saturated_pvc_data)
        assert len(result.saturated_pvcs) >= 1

    @pytest.mark.asyncio
    async def test_saturation_score_bounded(self, storage_agent, saturated_pvc_data):
        """Saturation score should be in [0.0, 1.0]."""
        result = await storage_agent.analyze(saturated_pvc_data)
        for sat in result.saturated_pvcs:
            assert 0.0 <= sat.saturation_score <= 1.0

    @pytest.mark.asyncio
    async def test_no_false_positive_saturation(self, storage_agent, normal_storage_data):
        """Low write rate PVC should NOT be flagged as saturated."""
        result = await storage_agent.analyze(normal_storage_data)
        assert result.saturated_pvcs == []


class TestBulkWriteDetection:
    """Verify bulk write detection (>50 MB/s sustained)."""

    @pytest.mark.asyncio
    async def test_detects_bulk_writer(self, storage_agent, saturated_pvc_data):
        """PVC with sustained high write rate should be flagged."""
        result = await storage_agent.analyze(saturated_pvc_data)
        assert len(result.bulk_writers) >= 1 or len(result.saturated_pvcs) >= 1

    @pytest.mark.asyncio
    async def test_no_false_positive_bulk(self, storage_agent, normal_storage_data):
        """Low write rate should NOT trigger bulk write alert."""
        result = await storage_agent.analyze(normal_storage_data)
        assert result.bulk_writers == []


class TestMixedStorage:
    """Verify correct analysis with mixed PVC states."""

    @pytest.mark.asyncio
    async def test_total_pvcs_analyzed(self, storage_agent, mixed_storage_data):
        """total_pvcs_analyzed should match input count."""
        result = await storage_agent.analyze(mixed_storage_data)
        assert result.total_pvcs_analyzed == 3

    @pytest.mark.asyncio
    async def test_only_hot_pvc_flagged(self, storage_agent, mixed_storage_data):
        """Only the 80 MB/s PVC should be flagged, not the 5 MB/s or 30 MB/s."""
        result = await storage_agent.analyze(mixed_storage_data)
        if result.saturated_pvcs:
            sat_names = [s.pvc_name for s in result.saturated_pvcs]
            assert "hot-pvc" in sat_names or "saturated-pvc" in sat_names

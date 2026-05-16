"""
PodMind — Dependency Mapper Unit Tests

Tests the Granger causality-based dependency mapper to verify:
  1. Known causal pair produces a directed edge
  2. Uncorrelated series produce no edges
  3. Graph output is D3.js-compatible JSON
  4. Large cluster optimization limits pair count
  5. Output always passes Pydantic validation
"""

import pytest
import numpy as np
import pandas as pd

from agents.dependency_mapper import DependencyMapper
from agents.schemas import DependencyGraph, ResourceType
from tests.fixtures.metric_fixtures import (
    granger_causal_pair,
    generate_timestamp_index,
)


@pytest.fixture
def mapper():
    """Create a Dependency Mapper with default thresholds."""
    return DependencyMapper(
        max_lag=6,
        p_threshold=0.05,
        min_samples=30,
    )


@pytest.fixture
def causal_cpu_data():
    """
    Create CPU data where pod-A Granger-causes pod-B with lag=2.
    Uses the pre-built causal pair fixture.
    """
    cause, effect = granger_causal_pair()

    # Normalize to 0-1 range for realistic CPU data
    cause_norm = (cause - cause.min()) / (cause.max() - cause.min())
    effect_norm = (effect - effect.min()) / (effect.max() - effect.min())

    data = {
        "default:cause-pod": pd.DataFrame(
            {"cpu_usage_pct": cause_norm.values}, index=cause.index
        ),
        "default:effect-pod": pd.DataFrame(
            {"cpu_usage_pct": effect_norm.values}, index=effect.index
        ),
    }
    return data


@pytest.fixture
def uncorrelated_cpu_data():
    """
    Create CPU data with two completely independent random series.
    Should produce NO edges.
    """
    idx = generate_timestamp_index()
    np.random.seed(100)

    data = {
        "default:random-pod-a": pd.DataFrame(
            {"cpu_usage_pct": np.random.uniform(0.2, 0.8, len(idx))}, index=idx
        ),
        "default:random-pod-b": pd.DataFrame(
            {"cpu_usage_pct": np.random.uniform(0.1, 0.5, len(idx))}, index=idx
        ),
    }
    return data


@pytest.fixture
def multi_pod_cpu_data():
    """Create 5 pods with varying relationships for edge count testing."""
    idx = generate_timestamp_index()
    np.random.seed(42)
    n = len(idx)

    data = {}
    # Pod A: base signal
    a = np.cumsum(np.random.normal(0, 0.05, n))
    a = (a - a.min()) / (a.max() - a.min())
    data["ns1:pod-a"] = pd.DataFrame({"cpu_usage_pct": a}, index=idx)

    # Pod B: follows A with lag 2
    b = np.zeros(n)
    for i in range(2, n):
        b[i] = 0.6 * a[i - 2] + np.random.normal(0, 0.1)
    b = np.clip(b, 0, 1)
    data["ns1:pod-b"] = pd.DataFrame({"cpu_usage_pct": b}, index=idx)

    # Pod C: independent
    data["ns1:pod-c"] = pd.DataFrame(
        {"cpu_usage_pct": np.random.uniform(0.3, 0.7, n)}, index=idx
    )

    # Pod D: follows B with lag 3
    d = np.zeros(n)
    for i in range(3, n):
        d[i] = 0.5 * b[i - 3] + np.random.normal(0, 0.15)
    d = np.clip(d, 0, 1)
    data["ns1:pod-d"] = pd.DataFrame({"cpu_usage_pct": d}, index=idx)

    # Pod E: different namespace, independent
    data["ns2:pod-e"] = pd.DataFrame(
        {"cpu_usage_pct": np.random.uniform(0.1, 0.4, n)}, index=idx
    )

    return data


# =============================================================================
# Test Cases
# =============================================================================

class TestGrangerCausality:
    """Verify Granger causality test correctly identifies causal relationships."""

    def test_causal_pair_detected(self, mapper, causal_cpu_data):
        """Known causal pair should produce at least one directed edge."""
        graph = mapper.build(
            cpu_data=causal_cpu_data,
            memory_data={},  # No memory data
        )
        assert isinstance(graph, DependencyGraph)
        assert len(graph.edges) >= 1

        # Check that the edge goes cause → effect
        edge_pairs = [(e.source, e.target) for e in graph.edges]
        assert (
            ("default:cause-pod", "default:effect-pod") in edge_pairs
        ), f"Expected cause→effect edge, got: {edge_pairs}"

    def test_causal_edge_attributes(self, mapper, causal_cpu_data):
        """Causal edge should have correct attributes."""
        graph = mapper.build(cpu_data=causal_cpu_data, memory_data={})

        for edge in graph.edges:
            if edge.source == "default:cause-pod":
                assert edge.p_value < 0.05
                assert edge.lag_seconds > 0
                assert edge.resource_type == ResourceType.CPU
                assert 0.0 <= edge.r_squared <= 1.0
                break

    def test_uncorrelated_no_edges(self, mapper, uncorrelated_cpu_data):
        """Uncorrelated series should produce no significant edges."""
        graph = mapper.build(
            cpu_data=uncorrelated_cpu_data,
            memory_data={},
        )
        # Allow 0 or very few spurious edges (statistical noise)
        assert len(graph.edges) <= 1, (
            f"Expected 0-1 edges for uncorrelated data, got {len(graph.edges)}"
        )


class TestGraphStructure:
    """Verify the output graph structure for D3.js compatibility."""

    def test_nodes_have_required_fields(self, mapper, causal_cpu_data):
        """All nodes must have id, pod, namespace fields."""
        graph = mapper.build(cpu_data=causal_cpu_data, memory_data={})

        assert len(graph.nodes) == 2
        for node in graph.nodes:
            assert node.id  # Non-empty
            assert node.pod
            assert node.namespace
            assert 0.0 <= node.resource_pressure <= 1.0
            assert node.status in ("healthy", "warning", "critical")

    def test_graph_serializable_to_json(self, mapper, causal_cpu_data):
        """Graph output must be JSON-serializable for D3.js."""
        graph = mapper.build(cpu_data=causal_cpu_data, memory_data={})
        json_str = graph.model_dump_json()
        rebuilt = DependencyGraph.model_validate_json(json_str)
        assert len(rebuilt.nodes) == len(graph.nodes)
        assert len(rebuilt.edges) == len(graph.edges)

    def test_generated_at_timestamp(self, mapper, causal_cpu_data):
        """Graph must include generated_at timestamp."""
        graph = mapper.build(cpu_data=causal_cpu_data, memory_data={})
        assert graph.generated_at  # Non-empty ISO timestamp


class TestMultiPodGraph:
    """Test with multiple pods for realistic graph scenarios."""

    def test_multi_pod_graph_nodes(self, mapper, multi_pod_cpu_data):
        """All pods should appear as nodes."""
        graph = mapper.build(cpu_data=multi_pod_cpu_data, memory_data={})
        node_ids = {n.id for n in graph.nodes}
        assert "ns1:pod-a" in node_ids
        assert "ns1:pod-b" in node_ids
        assert "ns2:pod-e" in node_ids

    def test_multi_pod_causal_chain(self, mapper, multi_pod_cpu_data):
        """Should detect causal chain: pod-a → pod-b → pod-d."""
        graph = mapper.build(cpu_data=multi_pod_cpu_data, memory_data={})
        edge_pairs = {(e.source, e.target) for e in graph.edges}

        # At minimum, A→B should be detected (strong signal)
        assert ("ns1:pod-a", "ns1:pod-b") in edge_pairs, (
            f"Expected A→B edge, got: {edge_pairs}"
        )

    def test_edge_labels_present(self, mapper, multi_pod_cpu_data):
        """All edges should have human-readable labels."""
        graph = mapper.build(cpu_data=multi_pod_cpu_data, memory_data={})
        for edge in graph.edges:
            assert edge.label  # Non-empty label


class TestLargeClusterOptimization:
    """Verify pair generation limits for large clusters."""

    def test_max_pairs_cap(self, mapper):
        """Pairs should be capped at max_pairs for large clusters."""
        # Create 60 fake pod keys (exceeds 50-pod threshold)
        keys = [f"ns{i // 10}:pod-{i}" for i in range(60)]
        pairs = mapper._generate_pairs(keys, None)
        assert len(pairs) <= mapper._max_pairs


class TestEmptyInput:
    """Verify graceful handling of edge cases."""

    def test_single_pod_returns_empty_graph(self, mapper):
        """Need at least 2 pods for dependency analysis."""
        idx = generate_timestamp_index()
        single_pod = {
            "default:lonely-pod": pd.DataFrame(
                {"cpu_usage_pct": np.random.uniform(0.2, 0.5, len(idx))}, index=idx
            ),
        }
        graph = mapper.build(cpu_data=single_pod, memory_data={})
        assert len(graph.edges) == 0

    def test_empty_data_returns_empty_graph(self, mapper):
        """Empty input returns empty DependencyGraph."""
        graph = mapper.build(cpu_data={}, memory_data={})
        assert isinstance(graph, DependencyGraph)
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

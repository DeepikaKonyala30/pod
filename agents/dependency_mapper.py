"""
PodMind — Dependency Mapper (Granger Causality)

Builds a directed dependency graph where each edge represents a
statistically significant causal relationship between two pods'
resource metrics, using the Granger causality test.

Algorithm (per SRS §5.3.6):
  1. For every pod pair (A, B), retrieve CPU/memory/network time-series
  2. Apply Granger causality test with max_lag=6 (30s), threshold p < 0.05
  3. If A Granger-causes B, add directed edge A → B with attributes
  4. For >50 pods, limit tests to same-namespace or network-connected pairs
  5. Output JSON-serializable graph for D3.js rendering

VULN-01 FIX: The Granger causality loop is offloaded to a thread pool
via asyncio.run_in_executor() to prevent blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
from itertools import combinations
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

from agents.schemas import (
    DependencyGraph,
    GraphEdge,
    GraphNode,
    ResourceType,
    Severity,
)

logger = logging.getLogger("podmind.agents.dependency_mapper")


class DependencyMapper:
    """
    Builds a causal dependency graph across pods using Granger causality.

    The graph is rendered as a D3.js force-directed layout in the dashboard.
    Edges encode resource type, lag, p-value, and causal strength (R²).

    VULN-01 FIX: The heavy Granger causality computations are offloaded
    to a background thread pool to prevent event loop starvation.
    """

    def __init__(
        self,
        max_lag: int = 6,
        p_threshold: float = 0.05,
        max_pairs: int = 500,
        min_samples: int = 30,
    ):
        """
        Args:
            max_lag: Maximum lag in samples for Granger test (6 × 5s = 30s).
            p_threshold: Significance threshold for Granger test.
            max_pairs: Maximum number of pod pairs to test (complexity limit).
            min_samples: Minimum time-series length for valid Granger test.
        """
        self._max_lag = max_lag
        self._p_threshold = p_threshold
        self._max_pairs = max_pairs
        self._min_samples = min_samples

    async def build_async(
        self,
        cpu_data: dict[str, pd.DataFrame],
        memory_data: dict[str, pd.DataFrame],
        network_data: dict[str, pd.DataFrame] | None = None,
        pod_metadata: list[dict[str, Any]] | None = None,
    ) -> DependencyGraph:
        """
        Async wrapper that offloads the heavy Granger computation to a thread pool.

        VULN-01 FIX: Prevents event loop starvation by running the CPU-bound
        statsmodels computations in a background thread.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.build, cpu_data, memory_data, network_data, pod_metadata
        )

    def build(
        self,
        cpu_data: dict[str, pd.DataFrame],
        memory_data: dict[str, pd.DataFrame],
        network_data: dict[str, pd.DataFrame] | None = None,
        pod_metadata: list[dict[str, Any]] | None = None,
    ) -> DependencyGraph:
        """
        Build the dependency graph from all resource time-series.

        Tests Granger causality across CPU, memory, and network dimensions
        for every eligible pod pair, then assembles a NetworkX graph
        converted to D3.js-compatible JSON.

        Args:
            cpu_data: Normalized CPU DataFrames per pod.
            memory_data: Normalized memory DataFrames per pod.
            network_data: Normalized network DataFrames per pod.
            pod_metadata: Pod info dicts for node attributes.
        """
        G = nx.DiGraph()

        # Collect all pod keys
        all_keys = set()
        all_keys.update(cpu_data.keys())
        all_keys.update(memory_data.keys())
        if network_data:
            all_keys.update(network_data.keys())

        if len(all_keys) < 2:
            logger.info("Need at least 2 pods for dependency analysis")
            return DependencyGraph()

        # Add nodes
        for key in all_keys:
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            ns, pod = parts
            G.add_node(key, pod=pod, namespace=ns)

        # Generate pod pairs (with optimization for large clusters)
        pairs = self._generate_pairs(list(all_keys), pod_metadata)

        logger.info(
            "Testing Granger causality on %d pairs (%d pods)",
            len(pairs), len(all_keys),
        )

        # Test each resource dimension
        resource_map = [
            (cpu_data, ResourceType.CPU, "cpu_usage_pct"),
            (memory_data, ResourceType.MEMORY, "memory_usage_ratio"),
        ]
        if network_data:
            resource_map.append(
                (network_data, ResourceType.NETWORK, "rx_rate")
            )

        edges_found = 0
        for data, resource_type, column in resource_map:
            for key_a, key_b in pairs:
                if key_a not in data or key_b not in data:
                    continue

                df_a = data[key_a]
                df_b = data[key_b]

                if df_a.empty or df_b.empty:
                    continue
                if column not in df_a.columns or column not in df_b.columns:
                    continue

                series_a = df_a[column].dropna().values
                series_b = df_b[column].dropna().values

                # Align lengths
                min_len = min(len(series_a), len(series_b))
                if min_len < self._min_samples:
                    continue

                series_a = series_a[:min_len]
                series_b = series_b[:min_len]

                # Test A → B
                result = self._test_granger(series_a, series_b)
                if result["significant"]:
                    parts_a = key_a.split(":", 1)
                    parts_b = key_b.split(":", 1)
                    G.add_edge(
                        key_a, key_b,
                        resource=resource_type.value,
                        p_value=result["p_value"],
                        lag_seconds=result["lag_seconds"],
                        r_squared=result.get("r_squared", 0.0),
                    )
                    edges_found += 1

                # Test B → A (reverse direction)
                result_rev = self._test_granger(series_b, series_a)
                if result_rev["significant"]:
                    G.add_edge(
                        key_b, key_a,
                        resource=resource_type.value,
                        p_value=result_rev["p_value"],
                        lag_seconds=result_rev["lag_seconds"],
                        r_squared=result_rev.get("r_squared", 0.0),
                    )
                    edges_found += 1

        logger.info("Dependency graph: %d nodes, %d edges", G.number_of_nodes(), edges_found)

        return self._to_schema(G)

    # -------------------------------------------------------------------------
    # Granger Causality Test
    # -------------------------------------------------------------------------

    def _test_granger(
        self,
        series_cause: np.ndarray,
        series_effect: np.ndarray,
    ) -> dict[str, Any]:
        """
        Test if series_cause Granger-causes series_effect.

        Args:
            series_cause: The potential cause time-series.
            series_effect: The potential effect time-series.

        Returns:
            {
                "significant": bool,
                "p_value": float,
                "lag_seconds": int,
                "best_lag": int,
                "r_squared": float,
            }
        """
        try:
            # Stack as [effect, cause] — statsmodels convention
            data = np.column_stack([series_effect, series_cause])

            # Add small noise to prevent singular matrix errors
            data += np.random.normal(0, 1e-10, data.shape)

            results = grangercausalitytests(
                data, maxlag=self._max_lag, verbose=False
            )

            # Find minimum p-value across all lags
            p_values = {}
            for lag in range(1, self._max_lag + 1):
                if lag in results:
                    p_values[lag] = results[lag][0]["ssr_ftest"][1]

            if not p_values:
                return {"significant": False, "p_value": 1.0, "lag_seconds": 0, "best_lag": 0}

            best_lag = min(p_values, key=p_values.get)
            min_p = p_values[best_lag]

            # Estimate R² from the F-test
            f_stat = results[best_lag][0]["ssr_ftest"][0]
            n = len(series_cause)
            r_squared = float(f_stat * best_lag / (n - 2 * best_lag - 1 + f_stat * best_lag))
            r_squared = max(0.0, min(r_squared, 1.0))

            return {
                "significant": min_p < self._p_threshold,
                "p_value": round(float(min_p), 6),
                "lag_seconds": best_lag * 5,  # Convert samples to seconds
                "best_lag": best_lag,
                "r_squared": round(r_squared, 4),
            }

        except Exception as e:
            logger.debug("Granger test failed: %s", str(e))
            return {"significant": False, "p_value": 1.0, "lag_seconds": 0, "best_lag": 0}

    # -------------------------------------------------------------------------
    # Pair Generation (with optimization)
    # -------------------------------------------------------------------------

    def _generate_pairs(
        self,
        keys: list[str],
        pod_metadata: list[dict[str, Any]] | None,
    ) -> list[tuple[str, str]]:
        """
        Generate pod pairs for Granger testing.

        For >50 pods, limit to same-namespace pairs to reduce O(n²) complexity.
        """
        if len(keys) <= 50:
            pairs = list(combinations(keys, 2))
        else:
            # Group by namespace and only test within-namespace pairs
            ns_groups: dict[str, list[str]] = {}
            for key in keys:
                ns = key.split(":")[0]
                ns_groups.setdefault(ns, []).append(key)

            pairs = []
            for ns_keys in ns_groups.values():
                pairs.extend(combinations(ns_keys, 2))

            logger.info(
                "Large cluster optimization: %d pairs (same-namespace only)",
                len(pairs),
            )

        # Cap at max_pairs
        if len(pairs) > self._max_pairs:
            import random
            random.seed(42)
            pairs = random.sample(pairs, self._max_pairs)
            logger.info("Capped pairs at %d", self._max_pairs)

        return pairs

    # -------------------------------------------------------------------------
    # Schema Conversion
    # -------------------------------------------------------------------------

    def _to_schema(self, G: nx.DiGraph) -> DependencyGraph:
        """Convert NetworkX graph to Pydantic DependencyGraph schema."""
        nodes = []
        for node_id, data in G.nodes(data=True):
            # Compute resource pressure from edge weights
            in_degree = G.in_degree(node_id)
            out_degree = G.out_degree(node_id)
            pressure = min((in_degree + out_degree) / 10.0, 1.0)

            status = "healthy"
            if in_degree > 2:
                status = "warning"
            if in_degree > 4:
                status = "critical"

            nodes.append(GraphNode(
                id=node_id,
                pod=data.get("pod", ""),
                namespace=data.get("namespace", ""),
                resource_pressure=round(pressure, 3),
                anomaly_count=in_degree,
                status=status,
            ))

        edges = []
        for source, target, data in G.edges(data=True):
            resource_str = data.get("resource", "cpu")
            try:
                resource = ResourceType(resource_str)
            except ValueError:
                resource = ResourceType.CPU

            lag = data.get("lag_seconds", 0)
            r_sq = data.get("r_squared", 0.0)

            edges.append(GraphEdge(
                source=source,
                target=target,
                resource_type=resource,
                p_value=data.get("p_value", 0.05),
                lag_seconds=lag,
                r_squared=r_sq,
                label=f"{resource.value}, {lag}s lag",
            ))

        return DependencyGraph(nodes=nodes, edges=edges)

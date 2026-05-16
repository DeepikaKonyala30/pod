"""
PodMind — Log Collector

Async pod log streaming that retrieves the last N lines of container logs
from all running pods. Logs are parsed for error patterns used by the
Network/Log Agent for error rate computation and connection exhaustion detection.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("podmind.collector.log_collector")

# Pre-compiled patterns for log analysis
ERROR_PATTERN = re.compile(
    r"\b(ERROR|FATAL|CRITICAL|PANIC|Exception|Traceback)\b",
    re.IGNORECASE,
)
WARN_PATTERN = re.compile(r"\b(WARN|WARNING)\b", re.IGNORECASE)
CONNECTION_PATTERN = re.compile(
    r"(connection refused|too many connections|pool exhausted|"
    r"connection reset|connection timed out|ECONNREFUSED|ECONNRESET|"
    r"no available connections|max retries exceeded)",
    re.IGNORECASE,
)
OOM_PATTERN = re.compile(r"(out of memory|OOM|oom-kill|memory allocation failed)", re.IGNORECASE)


class LogCollector:
    """
    Collects and pre-parses pod logs for the Network/Log Agent.

    Produces structured log summaries including error counts, warning counts,
    connection exhaustion signals, and OOM indicators per pod.
    """

    def __init__(self, k8s_client, tail_lines: int = 100, max_concurrent: int = 20):
        """
        Args:
            k8s_client: K8sClient instance for API access.
            tail_lines: Number of log lines to retrieve per pod.
            max_concurrent: Max concurrent log fetch operations.
        """
        self._k8s = k8s_client
        self._tail_lines = tail_lines
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def collect_all_pod_logs(
        self, pods: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """
        Collect and parse logs from all provided pods concurrently.

        Args:
            pods: List of pod info dicts (from K8sClient.list_all_pods).

        Returns:
            Dictionary mapping "namespace:pod" to a log summary:
            {
                "raw_lines": int,
                "error_count": int,
                "warn_count": int,
                "connection_errors": int,
                "oom_signals": int,
                "error_lines": list[str],     # first 10 error lines
                "connection_lines": list[str], # first 5 connection error lines
                "errors_per_minute": float,
                "collected_at": str,
            }
        """
        tasks = []
        for pod in pods:
            # Skip pods that aren't running
            if pod.get("phase") != "Running":
                continue
            tasks.append(
                self._collect_pod_log(pod["name"], pod["namespace"])
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        log_summaries = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Log collection failed: %s", str(result))
                continue
            if result:
                key = f"{result['namespace']}:{result['pod']}"
                log_summaries[key] = result

        logger.debug("Collected logs from %d pods", len(log_summaries))
        return log_summaries

    async def _collect_pod_log(
        self, pod_name: str, namespace: str
    ) -> dict[str, Any] | None:
        """Collect and parse logs from a single pod with concurrency limiting."""
        async with self._semaphore:
            raw_log = await self._k8s.get_pod_logs(
                name=pod_name,
                namespace=namespace,
                tail_lines=self._tail_lines,
            )

            if not raw_log:
                return None

            return self._parse_log(raw_log, pod_name, namespace)

    def _parse_log(
        self, raw_log: str, pod_name: str, namespace: str
    ) -> dict[str, Any]:
        """
        Parse raw log text into a structured summary.

        Counts error/warn/connection patterns and extracts sample lines
        for the agent to include in LLM prompts.
        """
        lines = raw_log.strip().split("\n")
        total_lines = len(lines)

        error_count = 0
        warn_count = 0
        connection_errors = 0
        oom_signals = 0
        error_lines = []
        connection_lines = []

        for line in lines:
            if ERROR_PATTERN.search(line):
                error_count += 1
                if len(error_lines) < 10:
                    # Strip timestamp prefix if present, keep message concise
                    error_lines.append(line[:200])

            if WARN_PATTERN.search(line):
                warn_count += 1

            if CONNECTION_PATTERN.search(line):
                connection_errors += 1
                if len(connection_lines) < 5:
                    connection_lines.append(line[:200])

            if OOM_PATTERN.search(line):
                oom_signals += 1

        # Estimate error rate: assume log covers ~collection_interval_logs (60s)
        # This is a rough estimate; precise rate requires timestamps in logs.
        errors_per_minute = float(error_count)  # Over ~1 minute of log tail

        return {
            "pod": pod_name,
            "namespace": namespace,
            "raw_lines": total_lines,
            "error_count": error_count,
            "warn_count": warn_count,
            "connection_errors": connection_errors,
            "oom_signals": oom_signals,
            "error_lines": error_lines,
            "connection_lines": connection_lines,
            "errors_per_minute": errors_per_minute,
            "has_connection_exhaustion": connection_errors > 0,
            "has_oom_signals": oom_signals > 0,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

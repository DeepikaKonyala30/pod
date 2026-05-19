"""
PodMind — Collector Service Entry Point

Orchestrates all data collection jobs using APScheduler with configurable
intervals. Runs as a long-lived async process, collecting metrics from
Prometheus, kubelet, Kubernetes API, and pod logs, normalizing them, and
writing to Redis TimeSeries and Streams.

Collection cadence (per SRS §5.2.1):
  - 5s:  CPU usage, memory RSS
  - 10s: Network rx/tx, PVC write rate
  - 30s: Pod metadata, PVC discovery, events
  - 60s: Container logs (last 100 lines)
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add project root to path for config imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from collector.k8s_client import K8sClient
from collector.prometheus_client import PrometheusClient
from collector.kubelet_client import KubeletClient
from collector.log_collector import LogCollector
from collector.normalizer import MetricNormalizer
from collector.redis_writer import RedisWriter

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
log_format = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    if settings.log_format == "text"
    else '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
)
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format=log_format,
    stream=sys.stdout,
)
logger = logging.getLogger("podmind.collector")


class CollectorService:
    """
    Main collector service that manages scheduled metric collection jobs.

    Lifecycle:
        1. Initialize all clients (K8s, Prometheus, kubelet, Redis)
        2. Register collection jobs with APScheduler
        3. Run the async event loop until shutdown signal
    """

    def __init__(self):
        # Clients
        self._k8s = K8sClient(
            in_cluster=settings.k8s_in_cluster,
            kubeconfig_path=settings.kubeconfig,
        )
        self._prom = PrometheusClient(prometheus_url=settings.prometheus_url)
        self._kubelet = KubeletClient()
        self._normalizer = MetricNormalizer(resample_interval="5s")
        self._redis = RedisWriter(
            redis_url=settings.redis_url,
            retention_ms=settings.metric_retention_ms,
            max_connections=settings.redis_max_connections,
        )
        self._log_collector = LogCollector(self._k8s, tail_lines=100)

        # Scheduler
        self._scheduler = AsyncIOScheduler()

        # State: cached pod/PVC lists (refreshed every 30s)
        self._pods: list[dict] = []
        self._pvcs: list[dict] = []
        self._cpu_limits: dict[str, float] = {}
        self._mem_limits: dict[str, float] = {}

        # Shutdown flag
        self._shutdown = asyncio.Event()

    # -------------------------------------------------------------------------
    # Collection Jobs
    # -------------------------------------------------------------------------

    async def collect_fast_metrics(self):
        """
        5-second interval: CPU usage + Memory RSS.
        These are the highest-frequency metrics for real-time dashboards.
        """
        try:
            # Fetch from Prometheus (10-sample window for current snapshot)
            cpu_usage, mem_rss = await asyncio.gather(
                self._prom.get_cpu_usage_all_pods(window_minutes=1),
                self._prom.get_memory_usage_all_pods(window_minutes=1),
            )

            # Normalize
            normalized_cpu = self._normalizer.normalize_cpu(cpu_usage, self._cpu_limits)
            normalized_mem = self._normalizer.normalize_memory(
                mem_rss, self._mem_limits
            )

            # Write to Redis
            cpu_count, mem_count = await asyncio.gather(
                self._redis.write_cpu_metrics(normalized_cpu),
                self._redis.write_memory_metrics(normalized_mem),
            )

            logger.debug(
                "Fast collection: %d CPU + %d memory points", cpu_count, mem_count
            )

        except Exception as e:
            logger.error("Fast metric collection failed: %s", str(e), exc_info=True)

    async def collect_medium_metrics(self):
        """
        10-second interval: Network rx/tx, PVC write rate.
        """
        try:
            net_rx, net_tx, net_pkts, fs_write = await asyncio.gather(
                self._prom.get_network_rx_all_pods(window_minutes=2),
                self._prom.get_network_tx_all_pods(window_minutes=2),
                self._prom.get_network_packets_all_pods(window_minutes=2),
                self._prom.get_fs_write_rate_all_pods(window_minutes=2),
            )

            normalized_net = self._normalizer.normalize_network(
                net_rx, net_tx, net_pkts
            )
            normalized_storage = self._normalizer.normalize_pvc(fs_write)

            net_count, stor_count = await asyncio.gather(
                self._redis.write_network_metrics(normalized_net),
                self._redis.write_storage_metrics(normalized_storage),
            )

            logger.debug(
                "Medium collection: %d network + %d storage points",
                net_count,
                stor_count,
            )

        except Exception as e:
            logger.error("Medium metric collection failed: %s", str(e), exc_info=True)

    async def collect_slow_metrics(self):
        """
        30-second interval: Pod metadata, PVC discovery, events, resource limits.
        """
        try:
            # Parallel discovery
            pods, pvcs, events = await asyncio.gather(
                self._k8s.list_all_pods(),
                self._k8s.list_all_pvcs(),
                self._k8s.list_recent_events(minutes=10),
            )

            # Update cached state
            self._pods = pods
            self._pvcs = pvcs

            # Refresh resource limits from Prometheus
            cpu_limits, mem_limits = await asyncio.gather(
                self._prom.get_cpu_limits_all_pods(),
                self._prom.get_memory_limits_all_pods(),
            )
            if not cpu_limits:
                cpu_limits = {
                    f"{pod['namespace']}:{pod['name']}": float(pod.get("cpu_limit") or 0.0)
                    for pod in pods
                    if float(pod.get("cpu_limit") or 0.0) > 0
                }
            if not mem_limits:
                mem_limits = {
                    f"{pod['namespace']}:{pod['name']}": float(pod.get("mem_limit") or 0.0)
                    for pod in pods
                    if float(pod.get("mem_limit") or 0.0) > 0
                }
            self._cpu_limits = cpu_limits
            self._mem_limits = mem_limits

            # Write metadata and events
            meta_count, event_count = await asyncio.gather(
                self._redis.write_pod_metadata(pods),
                self._redis.publish_events(events),
            )

            logger.info(
                "Slow collection: %d pods, %d PVCs, %d events, %d/%d limits",
                len(pods),
                len(pvcs),
                event_count,
                len(cpu_limits),
                len(mem_limits),
            )

        except Exception as e:
            logger.error("Slow metric collection failed: %s", str(e), exc_info=True)

    async def collect_logs(self):
        """
        60-second interval: Container logs (last 100 lines per pod).
        """
        try:
            if not self._pods:
                return

            log_summaries = await self._log_collector.collect_all_pod_logs(self._pods)
            count = await self._redis.publish_log_summaries(log_summaries)

            logger.debug("Log collection: %d pod log summaries published", count)

        except Exception as e:
            logger.error("Log collection failed: %s", str(e), exc_info=True)

    # -------------------------------------------------------------------------
    # Startup & Shutdown
    # -------------------------------------------------------------------------

    async def start(self):
        """Initialize clients and start the collection scheduler."""
        logger.info("=" * 60)
        logger.info("PodMind Collector Service starting...")
        logger.info("  Prometheus: %s", settings.prometheus_url)
        logger.info("  Redis:      %s", settings.redis_url)
        logger.info("  K8s mode:   %s", "in-cluster" if settings.k8s_in_cluster else "kubeconfig")
        logger.info("  Intervals:  fast=%ds, medium=%ds, slow=%ds, logs=%ds",
                     settings.collection_interval_fast,
                     settings.collection_interval_medium,
                     settings.collection_interval_slow,
                     settings.collection_interval_logs)
        logger.info("=" * 60)

        # Health checks
        prom_ok = await self._prom.is_healthy()
        redis_ok = await self._redis.is_healthy()
        logger.info("Prometheus healthy: %s", prom_ok)
        logger.info("Redis healthy:      %s", redis_ok)

        if not redis_ok:
            logger.error("Redis is not reachable. Exiting.")
            return

        # Run initial slow collection to populate caches
        logger.info("Running initial pod/PVC/limit discovery...")
        await self.collect_slow_metrics()

        # Register scheduled jobs
        self._scheduler.add_job(
            self.collect_fast_metrics,
            IntervalTrigger(seconds=settings.collection_interval_fast),
            id="fast_metrics",
            name="CPU/Memory (5s)",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self.collect_medium_metrics,
            IntervalTrigger(seconds=settings.collection_interval_medium),
            id="medium_metrics",
            name="Network/Storage (10s)",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self.collect_slow_metrics,
            IntervalTrigger(seconds=settings.collection_interval_slow),
            id="slow_metrics",
            name="Metadata/Events (30s)",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self.collect_logs,
            IntervalTrigger(seconds=settings.collection_interval_logs),
            id="log_collection",
            name="Logs (60s)",
            max_instances=1,
            coalesce=True,
        )

        self._scheduler.start()
        logger.info("Collector scheduler started with %d jobs",
                     len(self._scheduler.get_jobs()))

        # Wait for shutdown signal
        await self._shutdown.wait()

    async def stop(self):
        """Gracefully shutdown the collector service."""
        logger.info("Shutting down collector service...")
        self._scheduler.shutdown(wait=False)
        await self._prom.close()
        await self._redis.close()
        self._shutdown.set()
        logger.info("Collector service stopped.")


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

async def main():
    """Run the collector service with graceful shutdown handling."""
    service = CollectorService()

    # Handle SIGINT/SIGTERM for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.ensure_future(service.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await service.start()
    except KeyboardInterrupt:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())

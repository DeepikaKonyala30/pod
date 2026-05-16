"""
PodMind — Kubelet Stats Client

Direct kubelet /stats/summary API client for PVC-level IOPS and throughput
metrics that are not available through Prometheus/kube-state-metrics.

The kubelet exposes per-volume filesystem statistics including:
  - usedBytes, capacityBytes, availableBytes
  - inodesUsed, inodes, inodesFree
  - time (timestamp)

We derive IOPS estimates from the rate of change in usedBytes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("podmind.collector.kubelet")


class KubeletClient:
    """
    Kubelet /stats/summary API client for PVC and volume-level metrics.

    Connects to the kubelet API via the Kubernetes API server proxy
    (avoids direct node access and certificate issues).
    """

    def __init__(
        self,
        api_server_url: str = "https://kubernetes.default.svc",
        token_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token",
        verify_ssl: bool = False,
    ):
        """
        Args:
            api_server_url: Kubernetes API server URL for proxying.
            token_path: Path to ServiceAccount token (in-cluster).
            verify_ssl: Whether to verify TLS certificates.
        """
        self._api_server_url = api_server_url.rstrip("/")
        self._token_path = token_path
        self._verify_ssl = verify_ssl
        self._token: Optional[str] = None

    def _get_token(self) -> str:
        """Read the ServiceAccount token for API authentication."""
        if self._token is None:
            try:
                with open(self._token_path) as f:
                    self._token = f.read().strip()
            except FileNotFoundError:
                logger.warning(
                    "ServiceAccount token not found at %s; using empty token",
                    self._token_path,
                )
                self._token = ""
        return self._token

    async def get_node_stats(self, node_name: str) -> Optional[dict[str, Any]]:
        """
        Fetch /stats/summary from a specific node via API server proxy.

        Args:
            node_name: Name of the Kubernetes node.

        Returns:
            Parsed JSON response from kubelet, or None on failure.
        """
        url = (
            f"{self._api_server_url}/api/v1/nodes/{node_name}/proxy/stats/summary"
        )
        headers = {}
        token = self._get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(verify=self._verify_ssl) as client:
                response = await client.get(url, headers=headers, timeout=15.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch kubelet stats for node %s: %s", node_name, str(e))
            return None

    async def get_pod_volume_stats(self, node_name: str) -> list[dict[str, Any]]:
        """
        Extract per-pod, per-volume storage statistics from kubelet.

        Returns a flat list of volume stat records:
        {
            "pod": str,
            "namespace": str,
            "volume_name": str,
            "pvc_name": str | None,
            "capacity_bytes": int,
            "used_bytes": int,
            "available_bytes": int,
            "usage_ratio": float,
            "inodes_used": int,
            "inodes_total": int,
            "timestamp": str,
        }
        """
        stats = await self.get_node_stats(node_name)
        if not stats:
            return []

        volume_records = []
        for pod_stat in stats.get("pods", []):
            pod_ref = pod_stat.get("podRef", {})
            pod_name = pod_ref.get("name", "unknown")
            pod_namespace = pod_ref.get("namespace", "unknown")

            for vol_stat in pod_stat.get("volume", []):
                vol_name = vol_stat.get("name", "unknown")
                pvc_ref = vol_stat.get("pvcRef")
                pvc_name = pvc_ref.get("name") if pvc_ref else None

                capacity = vol_stat.get("capacityBytes", 0)
                used = vol_stat.get("usedBytes", 0)
                available = vol_stat.get("availableBytes", 0)
                inodes_used = vol_stat.get("inodesUsed", 0)
                inodes_total = vol_stat.get("inodes", 0)

                usage_ratio = (used / capacity) if capacity > 0 else 0.0

                volume_records.append({
                    "pod": pod_name,
                    "namespace": pod_namespace,
                    "volume_name": vol_name,
                    "pvc_name": pvc_name,
                    "capacity_bytes": capacity,
                    "used_bytes": used,
                    "available_bytes": available,
                    "usage_ratio": round(usage_ratio, 4),
                    "inodes_used": inodes_used,
                    "inodes_total": inodes_total,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        logger.debug(
            "Collected %d volume stats from node %s", len(volume_records), node_name
        )
        return volume_records

    async def get_pod_fs_stats(self, node_name: str) -> list[dict[str, Any]]:
        """
        Extract per-pod ephemeral and rootfs storage statistics.

        Returns records for pod-level ephemeral storage and per-container
        rootfs/logs usage — useful for detecting pods consuming excessive
        ephemeral storage.
        """
        stats = await self.get_node_stats(node_name)
        if not stats:
            return []

        fs_records = []
        for pod_stat in stats.get("pods", []):
            pod_ref = pod_stat.get("podRef", {})
            pod_name = pod_ref.get("name", "unknown")
            pod_namespace = pod_ref.get("namespace", "unknown")

            # Ephemeral storage (all containers + volumes combined)
            ephemeral = pod_stat.get("ephemeral-storage", {})
            if ephemeral:
                fs_records.append({
                    "pod": pod_name,
                    "namespace": pod_namespace,
                    "fs_type": "ephemeral",
                    "capacity_bytes": ephemeral.get("capacityBytes", 0),
                    "used_bytes": ephemeral.get("usedBytes", 0),
                    "available_bytes": ephemeral.get("availableBytes", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # Per-container rootfs and logs
            for container_stat in pod_stat.get("containers", []):
                container_name = container_stat.get("name", "unknown")
                rootfs = container_stat.get("rootfs", {})
                logs_fs = container_stat.get("logs", {})

                if rootfs:
                    fs_records.append({
                        "pod": pod_name,
                        "namespace": pod_namespace,
                        "container": container_name,
                        "fs_type": "rootfs",
                        "used_bytes": rootfs.get("usedBytes", 0),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                if logs_fs:
                    fs_records.append({
                        "pod": pod_name,
                        "namespace": pod_namespace,
                        "container": container_name,
                        "fs_type": "logs",
                        "used_bytes": logs_fs.get("usedBytes", 0),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

        return fs_records

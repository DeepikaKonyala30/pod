"""
PodMind — Kubernetes API Client

Async wrapper around the kubernetes-python SDK providing pod, PVC, event,
and metadata discovery across all namespaces. Handles both in-cluster
(ServiceAccount) and out-of-cluster (kubeconfig) authentication.

All methods return structured dictionaries ready for normalization and
Redis storage. Uses watch-based event streaming for real-time pod events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from kubernetes import client, config
from kubernetes.client import (
    CoreV1Api,
    V1Namespace,
    V1PersistentVolumeClaim,
    V1Pod,
)
from kubernetes.client.models import CoreV1Event
from kubernetes.client.rest import ApiException

logger = logging.getLogger("podmind.collector.k8s")


class K8sClient:
    """
    Kubernetes API client for PodMind data collection.

    Discovers pods, PVCs, events, and metadata across all namespaces.
    Designed for single-node clusters (Minikube, K3s, MicroK8s).
    """

    def __init__(self, in_cluster: bool = False, kubeconfig_path: Optional[str] = None):
        """
        Initialize the Kubernetes client.

        Args:
            in_cluster: If True, use in-cluster ServiceAccount auth.
            kubeconfig_path: Path to kubeconfig file (ignored if in_cluster=True).
        """
        if in_cluster:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        else:
            config.load_kube_config(config_file=kubeconfig_path)
            logger.info("Loaded kubeconfig from %s", kubeconfig_path or "default")

        self._core_v1 = CoreV1Api()
        self._apps_v1 = client.AppsV1Api()

    # -------------------------------------------------------------------------
    # Pod Discovery
    # -------------------------------------------------------------------------

    async def list_all_pods(self) -> list[dict[str, Any]]:
        """
        List all running pods across all namespaces.

        Returns a flat list of pod metadata dictionaries containing:
        name, namespace, status, labels, owner, containers, resource requests/limits,
        node assignment, restart count, and timestamps.
        """
        loop = asyncio.get_event_loop()
        try:
            pod_list = await loop.run_in_executor(
                None,
                lambda: self._core_v1.list_pod_for_all_namespaces(
                    watch=False,
                    timeout_seconds=30,
                ),
            )
        except ApiException as e:
            logger.error("Failed to list pods: %s", e.reason)
            return []

        pods = []
        for pod in pod_list.items:
            pods.append(self._extract_pod_info(pod))

        logger.debug("Discovered %d pods across all namespaces", len(pods))
        return pods

    def _extract_pod_info(self, pod: V1Pod) -> dict[str, Any]:
        """Extract structured pod information from a V1Pod object."""
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        # Determine owner reference (Deployment, ReplicaSet, StatefulSet, etc.)
        owner = None
        owner_kind = None
        if metadata.owner_references:
            ref = metadata.owner_references[0]
            owner = ref.name
            owner_kind = ref.kind

        # Aggregate resource requests and limits across all containers
        total_cpu_request = 0.0
        total_cpu_limit = 0.0
        total_mem_request = 0
        total_mem_limit = 0
        container_names = []

        for container in spec.containers:
            container_names.append(container.name)
            if container.resources:
                if container.resources.requests:
                    total_cpu_request += self._parse_cpu(
                        container.resources.requests.get("cpu", "0")
                    )
                    total_mem_request += self._parse_memory(
                        container.resources.requests.get("memory", "0")
                    )
                if container.resources.limits:
                    total_cpu_limit += self._parse_cpu(
                        container.resources.limits.get("cpu", "0")
                    )
                    total_mem_limit += self._parse_memory(
                        container.resources.limits.get("memory", "0")
                    )

        # Aggregate restart counts from container statuses
        restart_count = 0
        if status.container_statuses:
            restart_count = sum(cs.restart_count for cs in status.container_statuses)

        # Volume mounts — identify PVC associations
        pvc_names = []
        if spec.volumes:
            for vol in spec.volumes:
                if vol.persistent_volume_claim:
                    pvc_names.append(vol.persistent_volume_claim.claim_name)

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "uid": metadata.uid,
            "labels": dict(metadata.labels or {}),
            "annotations": dict(metadata.annotations or {}),
            "owner": owner,
            "owner_kind": owner_kind,
            "phase": status.phase,
            "pod_ip": status.pod_ip,
            "node_name": spec.node_name,
            "containers": container_names,
            "cpu_request": total_cpu_request,
            "cpu_limit": total_cpu_limit,
            "mem_request": total_mem_request,
            "mem_limit": total_mem_limit,
            "restart_count": restart_count,
            "pvc_names": pvc_names,
            "has_resource_limits": total_cpu_limit > 0 and total_mem_limit > 0,
            "start_time": (
                metadata.creation_timestamp.isoformat() if metadata.creation_timestamp else None
            ),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------------
    # PVC Discovery
    # -------------------------------------------------------------------------

    async def list_all_pvcs(self) -> list[dict[str, Any]]:
        """
        List all PersistentVolumeClaims across all namespaces.

        Returns PVC metadata including capacity, access modes, and bound status.
        """
        loop = asyncio.get_event_loop()
        try:
            pvc_list = await loop.run_in_executor(
                None,
                lambda: self._core_v1.list_persistent_volume_claim_for_all_namespaces(
                    watch=False,
                    timeout_seconds=30,
                ),
            )
        except ApiException as e:
            logger.error("Failed to list PVCs: %s", e.reason)
            return []

        pvcs = []
        for pvc in pvc_list.items:
            pvcs.append(self._extract_pvc_info(pvc))

        logger.debug("Discovered %d PVCs", len(pvcs))
        return pvcs

    def _extract_pvc_info(self, pvc: V1PersistentVolumeClaim) -> dict[str, Any]:
        """Extract structured PVC information."""
        capacity_bytes = 0
        if pvc.status and pvc.status.capacity:
            capacity_bytes = self._parse_memory(pvc.status.capacity.get("storage", "0"))

        return {
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "phase": pvc.status.phase if pvc.status else "Unknown",
            "access_modes": pvc.spec.access_modes or [],
            "storage_class": pvc.spec.storage_class_name,
            "capacity_bytes": capacity_bytes,
            "capacity_gb": round(capacity_bytes / (1024**3), 2) if capacity_bytes > 0 else 0,
            "volume_name": pvc.spec.volume_name,
            "labels": dict(pvc.metadata.labels or {}),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------------
    # Event Discovery
    # -------------------------------------------------------------------------

    async def list_recent_events(self, minutes: int = 10) -> list[dict[str, Any]]:
        """
        List Kubernetes events from the last N minutes across all namespaces.

        Focuses on pod-related events: restarts, OOM kills, evictions, failures.
        """
        loop = asyncio.get_event_loop()
        try:
            event_list = await loop.run_in_executor(
                None,
                lambda: self._core_v1.list_event_for_all_namespaces(
                    watch=False,
                    timeout_seconds=30,
                ),
            )
        except ApiException as e:
            logger.error("Failed to list events: %s", e.reason)
            return []

        cutoff = datetime.now(timezone.utc).timestamp() - (minutes * 60)
        events = []

        for event in event_list.items:
            event_time = self._get_event_time(event)
            if event_time and event_time.timestamp() >= cutoff:
                events.append(self._extract_event_info(event, event_time))

        logger.debug("Found %d events in last %d minutes", len(events), minutes)
        return events

    def _get_event_time(self, event: CoreV1Event) -> Optional[datetime]:
        """Get the most recent timestamp from an event."""
        return event.last_timestamp or event.event_time or event.first_timestamp

    def _extract_event_info(self, event: CoreV1Event, event_time: datetime) -> dict[str, Any]:
        """Extract structured event information."""
        return {
            "type": event.type,  # Normal, Warning
            "reason": event.reason,  # Killing, OOMKilling, Evicted, etc.
            "message": event.message,
            "namespace": event.metadata.namespace,
            "involved_object_kind": event.involved_object.kind if event.involved_object else None,
            "involved_object_name": event.involved_object.name if event.involved_object else None,
            "count": event.count or 1,
            "timestamp": event_time.isoformat(),
            "timestamp_unix": event_time.timestamp(),
            "is_pod_event": (
                event.involved_object.kind == "Pod" if event.involved_object else False
            ),
            "is_restart": event.reason in ("Killing", "BackOff", "Restarted"),
            "is_oom": event.reason == "OOMKilling" or (
                event.message and "OOM" in event.message.upper()
            ),
        }

    # -------------------------------------------------------------------------
    # Pod Logs
    # -------------------------------------------------------------------------

    async def get_pod_logs(
        self,
        name: str,
        namespace: str,
        tail_lines: int = 100,
    ) -> str:
        """
        Retrieve the last N lines of container logs from a pod.

        Args:
            name: Pod name.
            namespace: Pod namespace.
            tail_lines: Number of lines to retrieve from the end.

        Returns:
            Log text as a string, or empty string on failure.
        """
        loop = asyncio.get_event_loop()
        try:
            logs = await loop.run_in_executor(
                None,
                lambda: self._core_v1.read_namespaced_pod_log(
                    name=name,
                    namespace=namespace,
                    tail_lines=tail_lines,
                    timestamps=True,
                ),
            )
            return logs or ""
        except ApiException as e:
            logger.warning("Failed to get logs for %s/%s: %s", namespace, name, e.reason)
            return ""

    # -------------------------------------------------------------------------
    # Namespace Discovery
    # -------------------------------------------------------------------------

    async def list_namespaces(self) -> list[str]:
        """List all namespace names in the cluster."""
        loop = asyncio.get_event_loop()
        try:
            ns_list = await loop.run_in_executor(
                None,
                lambda: self._core_v1.list_namespace(watch=False, timeout_seconds=15),
            )
            return [ns.metadata.name for ns in ns_list.items]
        except ApiException as e:
            logger.error("Failed to list namespaces: %s", e.reason)
            return []

    # -------------------------------------------------------------------------
    # Utility: Resource Parsing
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_cpu(value: str) -> float:
        """
        Parse Kubernetes CPU resource string to cores (float).

        Examples:
            "500m"  → 0.5
            "2"     → 2.0
            "100m"  → 0.1
        """
        if not value or value == "0":
            return 0.0
        value = str(value).strip()
        if value.endswith("m"):
            return float(value[:-1]) / 1000.0
        return float(value)

    @staticmethod
    def _parse_memory(value: str) -> int:
        """
        Parse Kubernetes memory resource string to bytes (int).

        Examples:
            "128Mi" → 134217728
            "1Gi"   → 1073741824
            "512M"  → 512000000
        """
        if not value or value == "0":
            return 0
        value = str(value).strip()
        units = {
            "Ki": 1024,
            "Mi": 1024**2,
            "Gi": 1024**3,
            "Ti": 1024**4,
            "K": 1000,
            "M": 1000**2,
            "G": 1000**3,
            "T": 1000**4,
        }
        for suffix, multiplier in units.items():
            if value.endswith(suffix):
                return int(float(value[: -len(suffix)]) * multiplier)
        return int(float(value))

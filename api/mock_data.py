"""
PodMind — Synthetic Demo Data Generator

Produces realistic, continuously-evolving fake cluster metrics when
real Kubernetes/Prometheus data is unavailable. Data drifts each call
so the UI visibly updates every few seconds.

All output matches the same schemas as real data so no UI changes needed.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Pod Roster — realistic K8s workload names across namespaces
# ---------------------------------------------------------------------------
DEMO_PODS = [
    {"name": "api-gateway-7d9f8b-xk2p9",      "namespace": "default",     "node": "minikube", "phase": "Running"},
    {"name": "user-service-6c8b7f-m3n4q",      "namespace": "default",     "node": "minikube", "phase": "Running"},
    {"name": "order-processor-5f4d3c-r7t8y",   "namespace": "default",     "node": "minikube", "phase": "Running"},
    {"name": "payment-svc-4b2a1d-w9u0i",       "namespace": "default",     "node": "minikube", "phase": "Running"},
    {"name": "redis-cache-8c6e5b-v2n3m",        "namespace": "default",     "node": "minikube", "phase": "Running"},
    {"name": "postgres-primary-9a7d6c-p4l5k",  "namespace": "default",     "node": "minikube", "phase": "Running"},
    {"name": "ml-inference-3b1f2e-a8s9d",       "namespace": "ai",          "node": "minikube", "phase": "Running"},
    {"name": "data-pipeline-2d4g5h-k6j7h",     "namespace": "ai",          "node": "minikube", "phase": "Running"},
    {"name": "prometheus-0",                     "namespace": "monitoring",  "node": "minikube", "phase": "Running"},
    {"name": "grafana-6f8h9j-l2m3n",            "namespace": "monitoring",  "node": "minikube", "phase": "Running"},
    {"name": "coredns-7d8f9b-q4w5e",            "namespace": "kube-system", "node": "minikube", "phase": "Running"},
    {"name": "metrics-server-5c6d7e-r6t7y",     "namespace": "kube-system", "node": "minikube", "phase": "Running"},
]

# Persistent noise seeds so each pod has independent oscillation
_SEEDS: dict[str, float] = {
    p["name"]: random.uniform(0, 2 * math.pi) for p in DEMO_PODS
}

# Pods deliberately stressed for anomaly generation
STRESSED_PODS = {"ml-inference-3b1f2e-a8s9d", "order-processor-5f4d3c-r7t8y", "postgres-primary-9a7d6c-p4l5k"}


def _phase(pod_name: str, offset: float = 0.0) -> float:
    """Current oscillation phase for a pod (advances with wall-clock time)."""
    return _SEEDS[pod_name] + offset + time.time() * 0.05


def _cpu(pod_name: str) -> float:
    """Simulated CPU usage 0–100% with realistic patterns."""
    base = 75.0 if pod_name in STRESSED_PODS else 25.0
    wave = math.sin(_phase(pod_name)) * 15
    spike = random.gauss(0, 3)
    return max(1.0, min(99.0, base + wave + spike))


def _mem(pod_name: str) -> float:
    """Simulated memory usage ratio 0–1 with slow leak on stressed pods."""
    if pod_name == "ml-inference-3b1f2e-a8s9d":
        # Slow linear memory leak
        leak = (time.time() % 3600) / 3600 * 0.3
        return min(0.95, 0.45 + leak + random.gauss(0, 0.01))
    base = 0.60 if pod_name in STRESSED_PODS else 0.30
    wave = math.sin(_phase(pod_name, 1.2)) * 0.08
    return max(0.05, min(0.97, base + wave + random.gauss(0, 0.01)))


def _net_rx(pod_name: str) -> float:
    """Network RX bytes/sec."""
    base = 800_000 if pod_name == "api-gateway-7d9f8b-xk2p9" else 120_000
    return max(0, base + math.sin(_phase(pod_name, 2.3)) * base * 0.4 + random.gauss(0, 5000))


def _net_tx(pod_name: str) -> float:
    return max(0, _net_rx(pod_name) * random.uniform(0.4, 0.9))


def _status(cpu: float, mem: float) -> str:
    if cpu > 85 or mem > 0.88:
        return "critical"
    if cpu > 65 or mem > 0.70:
        return "warning"
    return "healthy"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_demo_pods() -> list[dict[str, Any]]:
    """Return pod list with live metric snapshots."""
    now = datetime.now(timezone.utc).isoformat()
    pods = []
    for p in DEMO_PODS:
        n = p["name"]
        cpu = _cpu(n)
        mem = _mem(n)
        pods.append({
            **p,
            "cpu_pct": round(cpu, 2),
            "memory_ratio": round(mem, 4),
            "net_rx_bps": round(_net_rx(n), 0),
            "net_tx_bps": round(_net_tx(n), 0),
            "status": _status(cpu, mem),
            "uptime_seconds": random.randint(3600, 86400),
            "restarts": 0 if p["phase"] == "Running" else random.randint(1, 5),
            "collected_at": now,
        })
    return pods


def get_demo_insight() -> dict[str, Any]:
    """Return a fully-formed InsightOutput-compatible dict."""
    t = time.time()
    # Rotate which pod is most critical so values visibly change
    rotation = int(t / 30) % 3  # changes every 30s

    root_causes = [
        {
            "rank": 1,
            "pod": "ml-inference-3b1f2e-a8s9d",
            "namespace": "ai",
            "resource": "memory",
            "description": f"Memory usage at {round(_mem('ml-inference-3b1f2e-a8s9d')*100,1)}% — steady upward trend indicates active memory leak. GC pressure increasing.",
            "severity": "critical",
            "confidence": round(0.88 + math.sin(t * 0.03) * 0.05, 2),
        },
        {
            "rank": 2,
            "pod": "order-processor-5f4d3c-r7t8y",
            "namespace": "default",
            "resource": "cpu",
            "description": f"CPU throttling detected at {round(_cpu('order-processor-5f4d3c-r7t8y'),1)}% — request limits too low for current batch workload.",
            "severity": "high",
            "confidence": round(0.79 + math.sin(t * 0.04) * 0.04, 2),
        },
        {
            "rank": 3,
            "pod": "postgres-primary-9a7d6c-p4l5k",
            "namespace": "default",
            "resource": "storage",
            "description": "PVC write I/O saturation on postgres-data-0. WAL write amplification detected. Consider connection pooling.",
            "severity": "high",
            "confidence": round(0.73 + math.sin(t * 0.06) * 0.03, 2),
        },
        {
            "rank": 4,
            "pod": "api-gateway-7d9f8b-xk2p9",
            "namespace": "default",
            "resource": "network",
            "description": "Elevated network RX — ingress traffic spike correlates with downstream CPU pressure on user-service.",
            "severity": "medium",
            "confidence": round(0.65 + math.sin(t * 0.07) * 0.04, 2),
        },
    ]

    recommendations = [
        {
            "pod": "ml-inference-3b1f2e-a8s9d",
            "namespace": "ai",
            "action": "kubectl set resources deployment/ml-inference --limits=memory=4Gi --requests=memory=2Gi",
            "priority": "immediate",
            "rationale": "Memory limit increase will prevent OOM kill. Monitor for 15 minutes after applying.",
        },
        {
            "pod": "order-processor-5f4d3c-r7t8y",
            "namespace": "default",
            "action": "kubectl set resources deployment/order-processor --limits=cpu=2000m --requests=cpu=500m",
            "priority": "immediate",
            "rationale": "Current CPU limit of 500m is too restrictive. Raising to 2000m eliminates throttling.",
        },
        {
            "pod": "postgres-primary-9a7d6c-p4l5k",
            "namespace": "default",
            "action": "Apply PgBouncer connection pooler. Increase PVC IOPS to 3000. Consider read replica.",
            "priority": "short-term",
            "rationale": "I/O saturation is the root bottleneck. Connection pooling reduces write amplification.",
        },
    ]

    eta_ml = round(45 - (time.time() % 45), 1)
    eta_pg = round(80 - (time.time() % 80), 1)

    forecast_alerts = [
        {
            "pod": "ml-inference-3b1f2e-a8s9d",
            "namespace": "ai",
            "resource": "memory",
            "eta_minutes": max(5.0, eta_ml),
            "predicted_event": "OOMKill",
            "confidence": round(0.84 + math.sin(t * 0.03) * 0.05, 2),
        },
        {
            "pod": "postgres-primary-9a7d6c-p4l5k",
            "namespace": "default",
            "resource": "storage",
            "eta_minutes": max(10.0, eta_pg),
            "predicted_event": "PVC capacity exhaustion",
            "confidence": round(0.71 + math.sin(t * 0.05) * 0.04, 2),
        },
    ]

    return {
        "root_causes": root_causes,
        "recommendations": recommendations,
        "forecast_alerts": forecast_alerts,
        "dependency_narrative": (
            "api-gateway is the ingress fanout point — high RX traffic cascades CPU load to "
            "user-service (Granger p=0.012, lag=8s) and order-processor (p=0.019, lag=15s). "
            "order-processor's DB write latency is correlated with postgres I/O saturation "
            "(p=0.007, lag=22s). ml-inference memory growth is independent — likely model cache leak."
        ),
        "summary": (
            f"Cluster under moderate stress: {len([c for c in root_causes if c['severity'] in ('critical','high')])} high-severity issues. "
            "ml-inference memory leak is the most urgent risk (OOMKill in <45min). "
            "Order-processor CPU throttling is degrading order throughput by ~23%."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_demo_graph() -> dict[str, Any]:
    """Return a DependencyGraph-compatible dict with Granger causality edges."""
    pods = get_demo_pods()
    pod_map = {p["name"]: p for p in pods}

    nodes = []
    for p in pods:
        cpu = p["cpu_pct"] / 100.0
        mem = p["memory_ratio"]
        pressure = round(max(cpu, mem), 3)
        nodes.append({
            "id": f"{p['namespace']}/{p['name']}",
            "pod": p["name"],
            "namespace": p["namespace"],
            "resource_pressure": pressure,
            "status": p["status"],
        })

    t = time.time()
    edges = [
        {
            "source": "default/api-gateway-7d9f8b-xk2p9",
            "target": "default/user-service-6c8b7f-m3n4q",
            "resource_type": "network",
            "lag_seconds": 8,
            "p_value": round(0.012 + math.sin(t * 0.01) * 0.002, 4),
            "r_squared": round(0.71 + math.sin(t * 0.02) * 0.03, 3),
            "label": "network → cpu",
        },
        {
            "source": "default/api-gateway-7d9f8b-xk2p9",
            "target": "default/order-processor-5f4d3c-r7t8y",
            "resource_type": "network",
            "lag_seconds": 15,
            "p_value": round(0.019 + math.sin(t * 0.015) * 0.002, 4),
            "r_squared": round(0.64 + math.sin(t * 0.025) * 0.02, 3),
            "label": "network → cpu",
        },
        {
            "source": "default/order-processor-5f4d3c-r7t8y",
            "target": "default/postgres-primary-9a7d6c-p4l5k",
            "resource_type": "storage",
            "lag_seconds": 22,
            "p_value": round(0.007 + math.sin(t * 0.02) * 0.001, 4),
            "r_squared": round(0.83 + math.sin(t * 0.03) * 0.02, 3),
            "label": "writes → I/O",
        },
        {
            "source": "default/user-service-6c8b7f-m3n4q",
            "target": "default/redis-cache-8c6e5b-v2n3m",
            "resource_type": "network",
            "lag_seconds": 5,
            "p_value": round(0.031 + math.sin(t * 0.012) * 0.003, 4),
            "r_squared": round(0.58 + math.sin(t * 0.018) * 0.03, 3),
            "label": "cache lookups",
        },
        {
            "source": "ai/ml-inference-3b1f2e-a8s9d",
            "target": "default/postgres-primary-9a7d6c-p4l5k",
            "resource_type": "storage",
            "lag_seconds": 30,
            "p_value": round(0.044 + math.sin(t * 0.017) * 0.004, 4),
            "r_squared": round(0.52 + math.sin(t * 0.02) * 0.04, 3),
            "label": "model reads",
        },
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_demo_agent_activity() -> dict[str, Any]:
    """Return per-agent analysis summary for the AgentActivityPanel."""
    t = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    cpu_val = _cpu("order-processor-5f4d3c-r7t8y")
    mem_val = _mem("ml-inference-3b1f2e-a8s9d") * 100

    return {
        "cycle_id": f"cycle-{int(t/30):06d}",
        "cycle_started_at": now_iso,
        "cycle_duration_ms": round(random.uniform(800, 2400), 0),
        "llm_tier_used": "Groq/llama-3.3-70b-versatile",
        "llm_latency_ms": round(random.uniform(420, 980), 0),
        "cpu_agent": {
            "status": "completed",
            "anomaly_count": 2,
            "throttled_count": 1,
            "top_pod": "order-processor-5f4d3c-r7t8y",
            "top_cpu_pct": round(cpu_val, 1),
            "latency_ms": round(random.uniform(80, 200), 0),
        },
        "memory_agent": {
            "status": "completed",
            "leak_suspects": 1,
            "oom_risk_count": 1,
            "top_pod": "ml-inference-3b1f2e-a8s9d",
            "memory_pct": round(mem_val, 1),
            "latency_ms": round(random.uniform(90, 220), 0),
        },
        "storage_agent": {
            "status": "completed",
            "saturated_pvcs": 1,
            "causal_hypotheses": 1,
            "top_pvc": "postgres-data-0",
            "saturation_score": round(0.72 + math.sin(t * 0.04) * 0.05, 3),
            "latency_ms": round(random.uniform(60, 180), 0),
        },
        "network_agent": {
            "status": "completed",
            "saturated_pods": 1,
            "chatty_pods": 1,
            "error_spikes": 0,
            "top_pod": "api-gateway-7d9f8b-xk2p9",
            "rx_mbps": round(_net_rx("api-gateway-7d9f8b-xk2p9") / 1e6, 2),
            "latency_ms": round(random.uniform(70, 190), 0),
        },
        "forecast_agent": {
            "status": "completed",
            "predictions": 2,
            "next_event": "OOMKill on ml-inference",
            "eta_minutes": round(max(5.0, 45 - (t % 45)), 1),
            "latency_ms": round(random.uniform(100, 300), 0),
        },
        "dependency_mapper": {
            "status": "completed",
            "nodes": 12,
            "edges": 5,
            "significant_edges": 3,
            "top_cause": "api-gateway → order-processor (network, lag=15s)",
            "latency_ms": round(random.uniform(200, 500), 0),
        },
    }

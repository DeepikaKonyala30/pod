"""
PodMind — Agent Pydantic Schemas

All input/output models for the multi-agent framework. Every agent produces
validated Pydantic output, ensuring type safety at every boundary between
agents, the orchestrator, the LLM, and the API layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Shared Enums
# =============================================================================

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ResourceType(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"


# =============================================================================
# Shared Records
# =============================================================================

class PodReference(BaseModel):
    """Identifies a specific pod in the cluster."""
    pod: str
    namespace: str


class AnomalyRecord(BaseModel):
    """A detected anomaly on a specific pod."""
    pod: str
    namespace: str
    anomaly_score: float = Field(ge=0.0, le=1.0, description="Isolation Forest score")
    reason: str = Field(description="Human-readable anomaly explanation")
    severity: Severity = Severity.MEDIUM


# =============================================================================
# CPU Agent Schemas
# =============================================================================

class ThrottleRecord(BaseModel):
    """A pod experiencing CPU throttling above threshold."""
    pod: str
    namespace: str
    throttle_pct: float = Field(ge=0.0, le=100.0, description="Throttle percentage")


class TrendRecord(BaseModel):
    """A pod trending toward its CPU limit."""
    pod: str
    namespace: str
    gradient: float = Field(description="Rate of change in CPU usage")
    eta_to_limit_min: Optional[float] = Field(
        default=None, description="Estimated minutes until limit is reached"
    )


class ConsumerRecord(BaseModel):
    """A top CPU consumer."""
    pod: str
    namespace: str
    p99_cpu_pct: float = Field(ge=0.0, description="p99 CPU usage percentage")


class CPUAgentOutput(BaseModel):
    """Output schema for the CPU Agent analysis."""
    anomalous_pods: list[AnomalyRecord] = Field(default_factory=list)
    throttled_pods: list[ThrottleRecord] = Field(default_factory=list)
    trending_pods: list[TrendRecord] = Field(default_factory=list)
    top_consumers: list[ConsumerRecord] = Field(default_factory=list)
    total_pods_analyzed: int = 0
    window_start: Optional[int] = None
    window_end: Optional[int] = None


# =============================================================================
# Memory Agent Schemas
# =============================================================================

class LeakRecord(BaseModel):
    """A pod suspected of having a memory leak."""
    pod: str
    namespace: str
    slope_pct_per_min: float = Field(description="Memory growth rate (% per minute)")
    current_usage_ratio: float = Field(ge=0.0, description="Current RSS/limit ratio")
    r_squared: float = Field(ge=0.0, le=1.0, description="Linear fit quality")


class OOMRiskRecord(BaseModel):
    """A pod at risk of OOM kill."""
    pod: str
    namespace: str
    usage_ratio: float = Field(ge=0.0, description="Current memory usage ratio")
    eta_oom_min: Optional[float] = Field(
        default=None, description="Estimated minutes to OOM"
    )


class CachePressureRecord(BaseModel):
    """A pod with high cache-to-RSS ratio (I/O-bound indicator)."""
    pod: str
    namespace: str
    cache_ratio: float = Field(ge=0.0, le=1.0, description="Cache/RSS ratio")


class RestartCorrelation(BaseModel):
    """A correlation between memory spike and pod restart event."""
    pod: str
    namespace: str
    restart_time: str
    memory_spike_pct: float
    correlation_strength: float = Field(ge=0.0, le=1.0)


class MemoryAgentOutput(BaseModel):
    """Output schema for the Memory Agent analysis."""
    leak_suspects: list[LeakRecord] = Field(default_factory=list)
    oom_risk_pods: list[OOMRiskRecord] = Field(default_factory=list)
    cache_pressure_pods: list[CachePressureRecord] = Field(default_factory=list)
    restart_correlations: list[RestartCorrelation] = Field(default_factory=list)
    total_pods_analyzed: int = 0
    window_start: Optional[int] = None
    window_end: Optional[int] = None


# =============================================================================
# Storage Agent Schemas
# =============================================================================

class PVCSaturationRecord(BaseModel):
    """A PVC experiencing I/O saturation."""
    pvc_name: str
    namespace: str
    saturation_score: float = Field(ge=0.0, le=1.0, description="IOPS saturation ratio")
    write_bytes_per_sec: float = Field(ge=0.0)
    pods_affected: list[str] = Field(default_factory=list)


class CausalHypothesis(BaseModel):
    """A causal hypothesis linking PVC saturation to a pod restart."""
    pod: str
    namespace: str
    pvc_name: str
    restart_time: str
    pvc_saturation_before_restart: float = Field(ge=0.0, le=1.0)
    hypothesis: str = Field(description="Human-readable causal explanation")
    confidence: float = Field(ge=0.0, le=1.0)


class BulkWriteRecord(BaseModel):
    """A pod performing large sequential writes."""
    pod: str
    namespace: str
    write_rate_mb_per_sec: float = Field(ge=0.0)
    duration_seconds: float = Field(ge=0.0)


class StorageAgentOutput(BaseModel):
    """Output schema for the Storage Agent analysis."""
    saturated_pvcs: list[PVCSaturationRecord] = Field(default_factory=list)
    restart_causal_hypotheses: list[CausalHypothesis] = Field(default_factory=list)
    bulk_writers: list[BulkWriteRecord] = Field(default_factory=list)
    total_pvcs_analyzed: int = 0
    window_start: Optional[int] = None
    window_end: Optional[int] = None


# =============================================================================
# Network / Log Agent Schemas
# =============================================================================

class NetworkSaturationRecord(BaseModel):
    """A pod with network saturation (rx or tx > 80% NIC capacity)."""
    pod: str
    namespace: str
    direction: str = Field(description="'rx' or 'tx'")
    saturation_pct: float = Field(ge=0.0, le=100.0)
    bytes_per_sec: float = Field(ge=0.0)


class ChattyPodRecord(BaseModel):
    """A pod with excessive packet rate (> 10k pkt/sec)."""
    pod: str
    namespace: str
    packets_per_sec: float = Field(ge=0.0)


class ErrorRateRecord(BaseModel):
    """A pod with elevated log error rate."""
    pod: str
    namespace: str
    errors_per_minute: float = Field(ge=0.0)
    error_samples: list[str] = Field(
        default_factory=list, description="First 5 error line samples"
    )


class ConnectionExhaustionRecord(BaseModel):
    """A pod showing connection pool exhaustion signals in logs."""
    pod: str
    namespace: str
    connection_error_count: int = Field(ge=0)
    sample_lines: list[str] = Field(default_factory=list)


class NetworkAgentOutput(BaseModel):
    """Output schema for the Network/Log Agent analysis."""
    saturated_pods: list[NetworkSaturationRecord] = Field(default_factory=list)
    chatty_pods: list[ChattyPodRecord] = Field(default_factory=list)
    error_rate_spikes: list[ErrorRateRecord] = Field(default_factory=list)
    connection_exhaustion: list[ConnectionExhaustionRecord] = Field(default_factory=list)
    total_pods_analyzed: int = 0
    window_start: Optional[int] = None
    window_end: Optional[int] = None


# =============================================================================
# Dependency Graph Schemas
# =============================================================================

class GraphNode(BaseModel):
    """A node in the dependency graph (represents a pod)."""
    id: str = Field(description="Format: namespace:pod")
    pod: str
    namespace: str
    resource_pressure: float = Field(
        ge=0.0, le=1.0, default=0.0,
        description="Composite resource pressure score for node sizing"
    )
    anomaly_count: int = Field(default=0)
    status: str = Field(default="healthy")


class GraphEdge(BaseModel):
    """A directed edge representing a causal relationship."""
    source: str = Field(description="Source node ID (cause)")
    target: str = Field(description="Target node ID (effect)")
    resource_type: ResourceType
    p_value: float = Field(ge=0.0, le=1.0)
    lag_seconds: int = Field(ge=0)
    r_squared: float = Field(ge=0.0, le=1.0, default=0.0, description="Causal strength")
    label: str = Field(default="", description="Human-readable edge label")


class DependencyGraph(BaseModel):
    """Complete dependency graph output for D3.js rendering."""
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# Forecast Schemas
# =============================================================================

class ForecastPoint(BaseModel):
    """A single forecast data point."""
    timestamp: str
    predicted_value: float
    lower_bound: float
    upper_bound: float


class PodForecast(BaseModel):
    """Resource forecast for a specific pod."""
    pod: str
    namespace: str
    resource_type: ResourceType
    forecast_points: list[ForecastPoint] = Field(default_factory=list)
    predicted_event: Optional[str] = Field(
        default=None, description="e.g., 'OOM kill', 'CPU throttle'"
    )
    eta_minutes: Optional[float] = Field(
        default=None, description="Minutes until predicted event"
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


# =============================================================================
# LLM Insight Schemas
# =============================================================================

class RootCause(BaseModel):
    """An identified root cause from LLM analysis."""
    rank: int = Field(ge=1)
    pod: str
    namespace: str
    resource: ResourceType
    description: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)


class Recommendation(BaseModel):
    """A concrete remediation recommendation."""
    pod: str
    namespace: str
    action: str
    priority: str = Field(description="'immediate', 'short-term', 'long-term'")
    rationale: Optional[str] = None


class ForecastAlert(BaseModel):
    """A predictive alert from forecasting."""
    pod: str
    namespace: str
    resource: ResourceType
    eta_minutes: float
    predicted_event: str
    confidence: float = Field(ge=0.0, le=1.0)


class InsightOutput(BaseModel):
    """Complete LLM-generated insight output."""
    root_causes: list[RootCause] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    forecast_alerts: list[ForecastAlert] = Field(default_factory=list)
    dependency_narrative: str = Field(default="")
    summary: str = Field(default="")
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# Orchestrator Aggregate Schema
# =============================================================================

class AnalysisCycleOutput(BaseModel):
    """Complete output of a single 30-second analysis cycle."""
    cpu: CPUAgentOutput
    memory: MemoryAgentOutput
    storage: StorageAgentOutput
    network: NetworkAgentOutput
    dependency_graph: DependencyGraph
    insights: Optional[InsightOutput] = None
    forecasts: list[PodForecast] = Field(default_factory=list)
    cycle_duration_ms: int = Field(ge=0, default=0)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

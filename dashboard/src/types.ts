export interface Pod {
  name: string;
  namespace: string;
  node?: string;
  phase?: string;
  cpu_pct: number;
  memory_ratio: number;
  net_rx_bps?: number;
  net_tx_bps?: number;
  status: 'healthy' | 'warning' | 'critical';
  restarts?: number;
  uptime_seconds?: number;
  collected_at?: string;
}

export interface RootCause {
  rank: number;
  pod: string;
  namespace: string;
  resource: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  confidence: number;
}

export interface Recommendation {
  pod: string;
  namespace: string;
  action: string;
  priority: 'immediate' | 'short-term' | 'long-term';
  rationale: string;
}

export interface ForecastAlert {
  pod: string;
  namespace: string;
  resource: string;
  eta_minutes: number;
  predicted_event: string;
  confidence: number;
}

export interface Insight {
  root_causes: RootCause[];
  recommendations: Recommendation[];
  forecast_alerts: ForecastAlert[];
  dependency_narrative: string;
  summary: string;
  generated_at: string;
}

export interface GraphNode {
  id: string;
  pod: string;
  namespace: string;
  resource_pressure: number;
  status: 'healthy' | 'warning' | 'critical';
}

export interface GraphEdge {
  source: string;
  target: string;
  resource_type: string;
  lag_seconds: number;
  p_value: number;
  r_squared: number;
  label: string;
}

export interface DependencyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  generated_at: string;
}

export interface SystemHealth {
  status: string;
  redis_connected: boolean;
  prometheus_connected: boolean;
  llm_tiers_available: string[];
}

export interface AgentStatus {
  status: 'completed' | 'running' | 'failed' | 'idle';
  anomaly_count?: number;
  throttled_count?: number;
  leak_suspects?: number;
  oom_risk_count?: number;
  saturated_pvcs?: number;
  causal_hypotheses?: number;
  saturated_pods?: number;
  chatty_pods?: number;
  error_spikes?: number;
  predictions?: number;
  nodes?: number;
  edges?: number;
  significant_edges?: number;
  top_pod?: string;
  top_pvc?: string;
  top_cpu_pct?: number;
  memory_pct?: number;
  saturation_score?: number;
  rx_mbps?: number;
  next_event?: string;
  eta_minutes?: number;
  top_cause?: string;
  latency_ms?: number;
}

export interface AgentActivity {
  cycle_id: string;
  cycle_started_at: string;
  cycle_duration_ms: number;
  llm_tier_used: string;
  llm_latency_ms: number;
  cpu_agent: AgentStatus;
  memory_agent: AgentStatus;
  storage_agent: AgentStatus;
  network_agent: AgentStatus;
  forecast_agent: AgentStatus;
  dependency_mapper: AgentStatus;
}

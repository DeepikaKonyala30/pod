export interface Pod {
  name: string;
  namespace: string;
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

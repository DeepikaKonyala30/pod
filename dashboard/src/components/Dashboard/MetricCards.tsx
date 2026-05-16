import type { Insight } from '../../types';
import { AlertCircle, Zap, Box, ArrowUpRight } from 'lucide-react';

export function MetricCards({ insight }: { insight: Insight | null }) {
  if (!insight) return null;

  const criticalCauses = insight.root_causes.filter(c => c.severity === 'critical').length;
  const highCauses = insight.root_causes.filter(c => c.severity === 'high').length;
  const totalAlerts = insight.forecast_alerts.length;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px' }}>
      <Card 
        title="Critical Anomalies" 
        value={criticalCauses} 
        icon={<AlertCircle color={criticalCauses > 0 ? "var(--status-critical)" : "var(--text-muted)"} />}
        color={criticalCauses > 0 ? "var(--status-critical)" : "var(--text-primary)"}
      />
      <Card 
        title="High Severity" 
        value={highCauses} 
        icon={<Zap color={highCauses > 0 ? "var(--status-high)" : "var(--text-muted)"} />}
        color={highCauses > 0 ? "var(--status-high)" : "var(--text-primary)"}
      />
      <Card 
        title="Predictive Alerts" 
        value={totalAlerts} 
        icon={<ArrowUpRight color={totalAlerts > 0 ? "var(--accent-purple)" : "var(--text-muted)"} />}
        color={totalAlerts > 0 ? "var(--accent-purple)" : "var(--text-primary)"}
      />
      <Card 
        title="Total Actions" 
        value={insight.recommendations.length} 
        icon={<Box color="var(--accent-blue)" />}
        color="var(--accent-blue)"
      />
    </div>
  );
}

function Card({ title, value, icon, color }: { title: string, value: number | string, icon: React.ReactNode, color: string }) {
  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {title}
        </span>
        {icon}
      </div>
      <div className="mono" style={{ fontSize: '2.5rem', fontWeight: 600, color, lineHeight: 1 }}>
        {value}
      </div>
    </div>
  );
}

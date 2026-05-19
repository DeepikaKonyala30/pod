import type { Insight, Pod } from '../../types';
import { AlertCircle, Zap, Box, ArrowUpRight, Server } from 'lucide-react';

interface Props {
  insight: Insight | null;
  pods: Pod[];
}

function SkeletonCard() {
  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ height: 12, width: 100, borderRadius: 6, background: 'rgba(255,255,255,0.07)', animation: 'pulse 1.5s ease-in-out infinite' }} />
        <div style={{ width: 20, height: 20, borderRadius: 4, background: 'rgba(255,255,255,0.07)', animation: 'pulse 1.5s ease-in-out infinite' }} />
      </div>
      <div style={{ height: 36, width: 60, borderRadius: 6, background: 'rgba(255,255,255,0.1)', animation: 'pulse 1.5s ease-in-out infinite' }} />
    </div>
  );
}

function Card({
  title, value, icon, color, subtext,
}: {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  color: string;
  subtext?: string;
}) {
  return (
    <div className="glass-panel" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{
          color: 'var(--text-secondary)', fontSize: '0.78rem', fontWeight: 500,
          textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          {title}
        </span>
        {icon}
      </div>
      <div className="mono" style={{ fontSize: '2.2rem', fontWeight: 700, color, lineHeight: 1, transition: 'color 0.4s' }}>
        {value}
      </div>
      {subtext && (
        <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: 0 }}>{subtext}</p>
      )}
    </div>
  );
}

export function MetricCards({ insight, pods }: Props) {
  if (!insight) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '20px' }}>
        {[0,1,2,3,4].map(i => <SkeletonCard key={i} />)}
      </div>
    );
  }

  const criticalCauses = insight.root_causes.filter(c => c.severity === 'critical').length;
  const highCauses     = insight.root_causes.filter(c => c.severity === 'high').length;
  const totalAlerts    = insight.forecast_alerts.length;
  const critPods       = pods.filter(p => p.status === 'critical').length;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '20px' }}>
      <Card
        title="Critical Anomalies"
        value={criticalCauses}
        icon={<AlertCircle size={18} color={criticalCauses > 0 ? 'var(--status-critical)' : 'var(--text-muted)'} />}
        color={criticalCauses > 0 ? 'var(--status-critical)' : 'var(--text-primary)'}
        subtext={criticalCauses > 0 ? 'Immediate action required' : 'All clear'}
      />
      <Card
        title="High Severity"
        value={highCauses}
        icon={<Zap size={18} color={highCauses > 0 ? 'var(--status-high)' : 'var(--text-muted)'} />}
        color={highCauses > 0 ? 'var(--status-high)' : 'var(--text-primary)'}
        subtext={highCauses > 0 ? 'Review recommended' : 'No issues'}
      />
      <Card
        title="Predictive Alerts"
        value={totalAlerts}
        icon={<ArrowUpRight size={18} color={totalAlerts > 0 ? 'var(--accent-purple)' : 'var(--text-muted)'} />}
        color={totalAlerts > 0 ? 'var(--accent-purple)' : 'var(--text-primary)'}
        subtext={totalAlerts > 0 ? 'Resource exhaustion forecast' : 'No forecasts'}
      />
      <Card
        title="AI Actions"
        value={insight.recommendations.length}
        icon={<Box size={18} color="var(--accent-blue)" />}
        color="var(--accent-blue)"
        subtext="Remediation steps ready"
      />
      <Card
        title="Active Pods"
        value={pods.length || '—'}
        icon={<Server size={18} color={critPods > 0 ? 'var(--status-critical)' : 'var(--status-info)'} />}
        color={critPods > 0 ? 'var(--status-high)' : 'var(--status-info)'}
        subtext={critPods > 0 ? `${critPods} pod${critPods > 1 ? 's' : ''} in critical state` : 'All pods healthy'}
      />
    </div>
  );
}

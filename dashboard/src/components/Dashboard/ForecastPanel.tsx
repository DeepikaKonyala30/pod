import type { Insight, ForecastAlert } from '../../types';
import { TrendingUp, Clock, Zap } from 'lucide-react';

export function ForecastPanel({ insight }: { insight: Insight | null }) {
  const alerts = insight?.forecast_alerts ?? [];

  if (alerts.length === 0) {
    return (
      <div className="glass-panel" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', minHeight: 200 }}>
        <div style={{ textAlign: 'center' }}>
          <TrendingUp size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
          <p>No resource exhaustion predicted.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '20px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <TrendingUp size={18} color="var(--accent-purple)" />
        <h3 style={{ fontSize: '1rem' }}>Forecast Alerts</h3>
        <span className="badge" style={{
          marginLeft: 'auto',
          padding: '4px 10px',
          fontSize: '0.75rem',
          background: 'var(--accent-purple-glow)',
          color: 'var(--accent-purple)',
        }}>
          {alerts.length} predicted
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {alerts.map((alert, i) => (
          <ForecastCard key={i} alert={alert} index={i} />
        ))}
      </div>
    </div>
  );
}

function ForecastCard({ alert, index }: { alert: ForecastAlert; index: number }) {
  const urgency = alert.eta_minutes < 15 ? 'critical' : alert.eta_minutes < 30 ? 'high' : 'medium';

  const urgencyColor: Record<string, string> = {
    critical: 'var(--status-critical)',
    high: 'var(--status-high)',
    medium: 'var(--accent-purple)',
  };

  const urgencyBg: Record<string, string> = {
    critical: 'rgba(239, 68, 68, 0.08)',
    high: 'rgba(245, 158, 11, 0.08)',
    medium: 'rgba(139, 92, 246, 0.08)',
  };

  return (
    <div
      className="animate-fade-in"
      style={{
        background: urgencyBg[urgency],
        border: `1px solid ${urgencyColor[urgency]}30`,
        borderRadius: 12,
        padding: '16px 18px',
        animationDelay: `${index * 0.15}s`,
        transition: 'transform 0.2s',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1.01)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1)'; }}
    >
      {/* Header Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Zap size={16} color={urgencyColor[urgency]} />
          <span className="mono" style={{ fontSize: '0.88rem', color: 'var(--text-primary)', fontWeight: 600 }}>
            {alert.pod}
          </span>
        </div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 12px',
          borderRadius: 20,
          background: `${urgencyColor[urgency]}20`,
          color: urgencyColor[urgency],
          fontWeight: 700,
          fontSize: '0.9rem',
        }}>
          <Clock size={14} />
          T-{alert.eta_minutes.toFixed(0)}m
        </div>
      </div>

      {/* Details */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0 0 6px 0' }}>
            Predicted <strong style={{ color: urgencyColor[urgency] }}>{alert.predicted_event}</strong> due to{' '}
            <span style={{ color: 'var(--accent-cyan)' }}>{alert.resource}</span> saturation
          </p>
          <div style={{ display: 'flex', gap: 12 }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Namespace: {alert.namespace}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Confidence: {(alert.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Progress bar showing time urgency */}
      <div style={{
        marginTop: 10,
        height: 3,
        borderRadius: 2,
        background: 'rgba(255,255,255,0.05)',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${Math.max(5, Math.min(100, 100 - alert.eta_minutes))}%`,
          background: `linear-gradient(90deg, ${urgencyColor[urgency]}, transparent)`,
          borderRadius: 2,
          transition: 'width 1s ease-out',
        }} />
      </div>
    </div>
  );
}

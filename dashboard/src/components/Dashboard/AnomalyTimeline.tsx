import type { Insight } from '../../types';
import { AlertTriangle, Activity } from 'lucide-react';

export function AnomalyTimeline({ insight }: { insight: Insight | null }) {
  if (!insight || insight.root_causes.length === 0) {
    return (
      <div className="glass-panel" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', minHeight: 200 }}>
        <div style={{ textAlign: 'center' }}>
          <Activity size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
          <p>No anomalies detected in current window.</p>
        </div>
      </div>
    );
  }

  const severityColor: Record<string, string> = {
    critical: 'var(--status-critical)',
    high: 'var(--status-high)',
    medium: 'var(--accent-purple)',
    low: 'var(--accent-blue)',
    info: 'var(--text-muted)',
  };

  const severityBg: Record<string, string> = {
    critical: 'rgba(239, 68, 68, 0.1)',
    high: 'rgba(245, 158, 11, 0.1)',
    medium: 'rgba(139, 92, 246, 0.1)',
    low: 'rgba(59, 130, 246, 0.1)',
    info: 'rgba(255, 255, 255, 0.03)',
  };

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '20px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <AlertTriangle size={18} color="var(--status-high)" />
        <h3 style={{ fontSize: '1rem' }}>Anomaly Timeline</h3>
        <span className="badge info" style={{ marginLeft: 'auto', padding: '4px 10px', fontSize: '0.75rem' }}>
          {insight.root_causes.length} active
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
        {/* Swimlane timeline */}
        <div style={{ position: 'relative', paddingLeft: 24 }}>
          {/* Vertical timeline line */}
          <div style={{
            position: 'absolute',
            left: 8,
            top: 0,
            bottom: 0,
            width: 2,
            background: 'linear-gradient(to bottom, var(--accent-purple), transparent)',
          }} />

          {insight.root_causes.map((cause, i) => (
            <div
              key={i}
              className="animate-fade-in"
              style={{
                position: 'relative',
                marginBottom: 16,
                animationDelay: `${i * 0.1}s`,
              }}
            >
              {/* Timeline dot */}
              <div style={{
                position: 'absolute',
                left: -20,
                top: 12,
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: severityColor[cause.severity] || 'var(--text-muted)',
                boxShadow: `0 0 8px ${severityColor[cause.severity] || 'transparent'}`,
                border: '2px solid var(--bg-primary)',
              }} />

              {/* Event card */}
              <div style={{
                background: severityBg[cause.severity] || 'transparent',
                border: `1px solid ${severityColor[cause.severity]}22`,
                borderRadius: 12,
                padding: '14px 16px',
                transition: 'transform 0.2s, box-shadow 0.2s',
              }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.transform = 'translateX(4px)';
                  (e.currentTarget as HTMLElement).style.boxShadow = `0 4px 12px ${severityColor[cause.severity]}15`;
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.transform = 'translateX(0)';
                  (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className={`badge ${cause.severity}`} style={{ fontSize: '0.7rem', padding: '2px 8px' }}>
                      {cause.severity.toUpperCase()}
                    </span>
                    <span style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)', fontWeight: 500 }}>
                      {cause.resource}
                    </span>
                  </div>
                  <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    #{cause.rank} • {(cause.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mono" style={{ fontSize: '0.82rem', color: 'var(--text-primary)', marginBottom: 4 }}>
                  {cause.namespace}/{cause.pod}
                </div>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.4 }}>
                  {cause.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

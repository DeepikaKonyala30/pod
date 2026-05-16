import type { Insight } from '../../types';
import { ShieldAlert, Lightbulb, Clock } from 'lucide-react';

export function InsightPanel({ insight }: { insight: Insight | null }) {
  if (!insight) {
    return (
      <div className="glass-panel" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        Awaiting initial AI analysis...
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '20px', borderBottom: '1px solid var(--border-light)' }}>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldAlert size={20} color="var(--accent-blue)" />
          AI Root Cause Analysis
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>{insight.summary}</p>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '12px', fontStyle: 'italic' }}>
          {insight.dependency_narrative}
        </p>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        
        {/* Root Causes */}
        {insight.root_causes.length > 0 && (
          <div>
            <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '12px', letterSpacing: '0.05em' }}>Identified Issues</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {insight.root_causes.map((cause, i) => (
                <div key={i} style={{ 
                  background: 'rgba(255,255,255,0.02)', 
                  border: '1px solid var(--border-light)', 
                  borderRadius: '12px', padding: '16px' 
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span className={`badge ${cause.severity}`}>{cause.severity}</span>
                      <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>{cause.namespace}/{cause.pod}</span>
                    </div>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Conf: {(cause.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{cause.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recommendations */}
        {insight.recommendations.length > 0 && (
          <div>
            <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '12px', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Lightbulb size={14} /> Actionable Recommendations
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {insight.recommendations.map((rec, i) => (
                <div key={i} style={{ 
                  background: 'linear-gradient(90deg, rgba(59,130,246,0.05), transparent)', 
                  borderLeft: '2px solid var(--accent-blue)', 
                  borderRadius: '0 12px 12px 0', padding: '16px' 
                }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                    <span className="badge" style={{ background: 'var(--accent-blue-glow)', color: 'var(--accent-blue)' }}>{rec.priority}</span>
                    <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>{rec.pod}</span>
                  </div>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '8px' }}>{rec.action}</p>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{rec.rationale}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Forecast Alerts */}
        {insight.forecast_alerts.length > 0 && (
          <div>
            <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '12px', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Clock size={14} /> Predictive Alerts
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {insight.forecast_alerts.map((alert, i) => (
                <div key={i} style={{ 
                  background: 'rgba(139,92,246,0.05)', 
                  border: '1px solid rgba(139,92,246,0.2)', 
                  borderRadius: '12px', padding: '16px' 
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span className="mono" style={{ fontSize: '0.85rem', color: 'var(--accent-purple)' }}>{alert.pod}</span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-primary)', fontWeight: 600 }}>T-{alert.eta_minutes.toFixed(0)}m</span>
                  </div>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Predicted {alert.predicted_event} due to {alert.resource} saturation.</p>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

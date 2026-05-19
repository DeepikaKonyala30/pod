import { useState } from 'react';
import type { Pod } from '../../types';
import { Server } from 'lucide-react';

const NS_COLORS: Record<string, string> = {
  default:     '#3b82f6',
  'kube-system': '#8b5cf6',
  monitoring:  '#06b6d4',
  ai:          '#f59e0b',
};

function nsColor(ns: string) { return NS_COLORS[ns] ?? '#6b7280'; }

function MiniBar({ value, max = 100, color, label }: {
  value: number; max?: number; color: string; label: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', width: 26, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.07)', overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: color,
          borderRadius: 3,
          transition: 'width 0.6s ease',
          boxShadow: `0 0 6px ${color}88`,
        }} />
      </div>
      <span style={{ fontSize: '0.68rem', color, width: 34, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
        {value.toFixed(1)}{max === 100 ? '%' : ''}
      </span>
    </div>
  );
}

function PodCard({ pod }: { pod: Pod }) {
  const [hovered, setHovered] = useState(false);

  const statusColor = pod.status === 'critical' ? 'var(--status-critical)'
    : pod.status === 'warning' ? 'var(--status-high)'
    : 'var(--status-info)';

  const cpuColor = pod.cpu_pct > 80 ? 'var(--status-critical)'
    : pod.cpu_pct > 60 ? 'var(--status-high)'
    : 'var(--accent-cyan)';

  const memColor = pod.memory_ratio > 0.85 ? 'var(--status-critical)'
    : pod.memory_ratio > 0.70 ? 'var(--status-high)'
    : 'var(--accent-purple)';

  const shortName = pod.name.length > 24
    ? pod.name.substring(0, 21) + '…'
    : pod.name;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.03)',
        border: `1px solid ${hovered ? statusColor + '55' : 'rgba(255,255,255,0.08)'}`,
        borderRadius: 12,
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        transition: 'all 0.2s ease',
        transform: hovered ? 'translateY(-2px)' : 'none',
        boxShadow: hovered ? `0 4px 16px ${statusColor}22` : 'none',
        cursor: 'default',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Status pulse dot */}
      <div style={{
        position: 'absolute', top: 10, right: 10,
        width: 7, height: 7, borderRadius: '50%',
        background: statusColor,
        boxShadow: `0 0 ${pod.status === 'critical' ? 8 : 4}px ${statusColor}`,
        animation: pod.status !== 'healthy' ? 'pulse 2s infinite' : 'none',
      }} />

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingRight: 16 }}>
        <Server size={13} color="var(--text-muted)" />
        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'monospace' }}>
          {shortName}
        </span>
      </div>

      {/* Namespace badge */}
      <div style={{
        display: 'inline-flex', alignItems: 'center',
        background: nsColor(pod.namespace) + '22',
        border: `1px solid ${nsColor(pod.namespace)}44`,
        borderRadius: 20, padding: '2px 8px',
        width: 'fit-content',
      }}>
        <span style={{ fontSize: '0.65rem', color: nsColor(pod.namespace), fontWeight: 500 }}>
          {pod.namespace}
        </span>
      </div>

      {/* Metrics bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <MiniBar value={pod.cpu_pct} max={100} color={cpuColor} label="CPU" />
        <MiniBar value={pod.memory_ratio * 100} max={100} color={memColor} label="MEM" />
      </div>
    </div>
  );
}

export function PodGrid({ pods }: { pods: Pod[] }) {
  const [nsFilter, setNsFilter] = useState<string>('all');

  const namespaces = ['all', ...Array.from(new Set(pods.map(p => p.namespace))).sort()];
  const filtered = nsFilter === 'all' ? pods : pods.filter(p => p.namespace === nsFilter);

  const critCount = pods.filter(p => p.status === 'critical').length;
  const warnCount = pods.filter(p => p.status === 'warning').length;

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Server size={16} color="var(--accent-cyan)" />
        <h3 style={{ fontSize: '1rem', marginRight: 'auto' }}>Live Pod Grid</h3>

        {/* Status summary */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {critCount > 0 && (
            <span className="badge critical" style={{ fontSize: '0.7rem', padding: '2px 8px' }}>
              {critCount} critical
            </span>
          )}
          {warnCount > 0 && (
            <span className="badge high" style={{ fontSize: '0.7rem', padding: '2px 8px' }}>
              {warnCount} warning
            </span>
          )}
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{pods.length} pods</span>
        </div>

        {/* NS filter pills */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {namespaces.map(ns => (
            <button
              key={ns}
              onClick={() => setNsFilter(ns)}
              style={{
                padding: '3px 10px', borderRadius: 20, border: 'none',
                fontSize: '0.7rem', cursor: 'pointer', transition: 'all 0.15s',
                background: nsFilter === ns
                  ? (ns === 'all' ? 'var(--accent-cyan)' : nsColor(ns))
                  : 'rgba(255,255,255,0.06)',
                color: nsFilter === ns ? '#000' : 'var(--text-muted)',
                fontWeight: nsFilter === ns ? 600 : 400,
              }}
            >
              {ns}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '16px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 10,
        alignContent: 'start',
      }}>
        {filtered.length === 0 ? (
          <div style={{ gridColumn: '1/-1', textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            <Server size={32} style={{ opacity: 0.2, marginBottom: 8 }} />
            <p>No pods in namespace "{nsFilter}"</p>
          </div>
        ) : (
          filtered.map(pod => (
            <PodCard key={`${pod.namespace}/${pod.name}`} pod={pod} />
          ))
        )}
      </div>
    </div>
  );
}

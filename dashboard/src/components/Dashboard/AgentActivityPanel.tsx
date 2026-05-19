import type { AgentActivity, AgentStatus } from '../../types';
import { Cpu, MemoryStick, HardDrive, Wifi, TrendingUp, GitBranch, Brain, CheckCircle2, Loader2, Clock } from 'lucide-react';

function ConfidenceBar({ value, color }: { value: number; color: string }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <div style={{ height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.07)', overflow: 'hidden', flex: 1 }}>
      <div style={{
        height: '100%', width: `${pct}%`, background: color,
        borderRadius: 2, transition: 'width 0.8s ease',
        boxShadow: `0 0 4px ${color}88`,
      }} />
    </div>
  );
}

interface AgentCardProps {
  name: string;
  icon: React.ReactNode;
  color: string;
  status: AgentStatus;
  stats: { label: string; value: string | number; highlight?: boolean }[];
  latency?: number;
}

function AgentCard({ name, icon, color, status, stats, latency }: AgentCardProps) {
  const isRunning  = status.status === 'running';
  const isComplete = status.status === 'completed';

  const statusEl = isRunning ? (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--accent-cyan)', fontSize: '0.7rem' }}>
      <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> Running
    </div>
  ) : isComplete ? (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--status-info)', fontSize: '0.7rem' }}>
      <CheckCircle2 size={11} /> Done
    </div>
  ) : (
    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Idle</div>
  );

  return (
    <div style={{
      background: `linear-gradient(135deg, ${color}0d, rgba(255,255,255,0.02))`,
      border: `1px solid ${color}33`,
      borderRadius: 12, padding: '14px 16px',
      display: 'flex', flexDirection: 'column', gap: 10,
      transition: 'border-color 0.3s',
    }}>
      {/* Agent header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: `1px solid ${color}44`,
        }}>
          {icon}
        </div>
        <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>{name}</span>
        {statusEl}
      </div>

      {/* Stats grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px' }}>
        {stats.map(s => (
          <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{s.label}</span>
            <span style={{
              fontSize: '0.72rem', fontWeight: 600, fontVariantNumeric: 'tabular-nums',
              color: s.highlight ? color : 'var(--text-primary)',
            }}>
              {s.value}
            </span>
          </div>
        ))}
      </div>

      {/* Latency */}
      {latency !== undefined && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <Clock size={10} color="var(--text-muted)" />
          <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
            {latency.toLocaleString()}ms
          </span>
          <ConfidenceBar value={latency / 3000} color={color} />
        </div>
      )}
    </div>
  );
}

export function AgentActivityPanel({ activity }: { activity: AgentActivity | null }) {
  if (!activity) {
    return (
      <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '20px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Brain size={18} color="var(--accent-purple)" />
          <h3 style={{ fontSize: '1rem' }}>AI Agent Intelligence</h3>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, color: 'var(--text-muted)' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {[0,1,2].map(i => (
              <div key={i} style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-purple)', opacity: 0.4, animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite` }} />
            ))}
          </div>
          <p style={{ fontSize: '0.85rem' }}>Initializing agents…</p>
        </div>
      </div>
    );
  }

  const cycleMs = activity.cycle_duration_ms;
  const cycleAt = new Date(activity.cycle_started_at).toLocaleTimeString();

  const agents: AgentCardProps[] = [
    {
      name: 'CPU Agent',
      icon: <Cpu size={14} color="#06b6d4" />,
      color: '#06b6d4',
      status: activity.cpu_agent,
      latency: activity.cpu_agent.latency_ms,
      stats: [
        { label: 'Anomalies',  value: activity.cpu_agent.anomaly_count ?? 0,  highlight: (activity.cpu_agent.anomaly_count ?? 0) > 0 },
        { label: 'Throttled',  value: activity.cpu_agent.throttled_count ?? 0, highlight: (activity.cpu_agent.throttled_count ?? 0) > 0 },
        ...(activity.cpu_agent.top_pod ? [{ label: 'Top Pod', value: activity.cpu_agent.top_pod.split('-').slice(0,2).join('-') }] : []),
        ...(activity.cpu_agent.top_cpu_pct !== undefined ? [{ label: 'Peak CPU', value: `${activity.cpu_agent.top_cpu_pct}%`, highlight: (activity.cpu_agent.top_cpu_pct ?? 0) > 70 }] : []),
      ],
    },
    {
      name: 'Memory Agent',
      icon: <MemoryStick size={14} color="#8b5cf6" />,
      color: '#8b5cf6',
      status: activity.memory_agent,
      latency: activity.memory_agent.latency_ms,
      stats: [
        { label: 'Leak suspects', value: activity.memory_agent.leak_suspects ?? 0, highlight: (activity.memory_agent.leak_suspects ?? 0) > 0 },
        { label: 'OOM risk',      value: activity.memory_agent.oom_risk_count ?? 0, highlight: (activity.memory_agent.oom_risk_count ?? 0) > 0 },
        ...(activity.memory_agent.memory_pct !== undefined ? [{ label: 'Peak MEM', value: `${activity.memory_agent.memory_pct?.toFixed(1)}%`, highlight: (activity.memory_agent.memory_pct ?? 0) > 75 }] : []),
      ],
    },
    {
      name: 'Storage Agent',
      icon: <HardDrive size={14} color="#f59e0b" />,
      color: '#f59e0b',
      status: activity.storage_agent,
      latency: activity.storage_agent.latency_ms,
      stats: [
        { label: 'Saturated PVCs', value: activity.storage_agent.saturated_pvcs ?? 0,    highlight: (activity.storage_agent.saturated_pvcs ?? 0) > 0 },
        { label: 'Hypotheses',     value: activity.storage_agent.causal_hypotheses ?? 0 },
        ...(activity.storage_agent.saturation_score !== undefined ? [{ label: 'I/O Saturation', value: `${((activity.storage_agent.saturation_score ?? 0)*100).toFixed(0)}%`, highlight: (activity.storage_agent.saturation_score ?? 0) > 0.6 }] : []),
      ],
    },
    {
      name: 'Network Agent',
      icon: <Wifi size={14} color="#10b981" />,
      color: '#10b981',
      status: activity.network_agent,
      latency: activity.network_agent.latency_ms,
      stats: [
        { label: 'Saturated',  value: activity.network_agent.saturated_pods ?? 0, highlight: (activity.network_agent.saturated_pods ?? 0) > 0 },
        { label: 'Chatty',     value: activity.network_agent.chatty_pods ?? 0 },
        { label: 'Err spikes', value: activity.network_agent.error_spikes ?? 0, highlight: (activity.network_agent.error_spikes ?? 0) > 0 },
        ...(activity.network_agent.rx_mbps !== undefined ? [{ label: 'Peak RX', value: `${activity.network_agent.rx_mbps} MB/s` }] : []),
      ],
    },
    {
      name: 'Forecast Agent',
      icon: <TrendingUp size={14} color="#f43f5e" />,
      color: '#f43f5e',
      status: activity.forecast_agent,
      latency: activity.forecast_agent.latency_ms,
      stats: [
        { label: 'Predictions',  value: activity.forecast_agent.predictions ?? 0, highlight: (activity.forecast_agent.predictions ?? 0) > 0 },
        ...(activity.forecast_agent.next_event ? [{ label: 'Next event', value: activity.forecast_agent.next_event.substring(0, 14) + '…' }] : []),
        ...(activity.forecast_agent.eta_minutes !== undefined ? [{ label: 'ETA', value: `${activity.forecast_agent.eta_minutes}m`, highlight: (activity.forecast_agent.eta_minutes ?? 99) < 30 }] : []),
      ],
    },
    {
      name: 'Dependency Mapper',
      icon: <GitBranch size={14} color="#3b82f6" />,
      color: '#3b82f6',
      status: activity.dependency_mapper,
      latency: activity.dependency_mapper.latency_ms,
      stats: [
        { label: 'Nodes',      value: activity.dependency_mapper.nodes ?? 0 },
        { label: 'Edges',      value: activity.dependency_mapper.edges ?? 0 },
        { label: 'Causal',     value: activity.dependency_mapper.significant_edges ?? 0, highlight: (activity.dependency_mapper.significant_edges ?? 0) > 0 },
      ],
    },
  ];

  return (
    <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: 'linear-gradient(135deg, var(--accent-purple), var(--accent-cyan))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 0 10px var(--accent-purple)44',
        }}>
          <Brain size={14} color="#000" />
        </div>
        <h3 style={{ fontSize: '1rem', flex: 1 }}>AI Agent Intelligence</h3>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Last cycle: {cycleAt}</div>
          <div style={{ fontSize: '0.68rem', color: 'var(--accent-cyan)' }}>{cycleMs.toLocaleString()}ms</div>
        </div>
      </div>

      {/* LLM tier badge */}
      <div style={{ padding: '8px 20px', background: 'rgba(139,92,246,0.05)', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Brain size={12} color="var(--accent-purple)" />
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>LLM Tier:</span>
        <span style={{ fontSize: '0.72rem', color: 'var(--accent-purple)', fontWeight: 600 }}>{activity.llm_tier_used}</span>
        <span style={{ marginLeft: 'auto', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
          {activity.llm_latency_ms.toLocaleString()}ms inference
        </span>
      </div>

      {/* Agent cards grid */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '14px 16px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: 10,
        alignContent: 'start',
      }}>
        {agents.map(a => <AgentCard key={a.name} {...a} />)}
      </div>

      {/* Active analysis ticker */}
      <div style={{
        padding: '8px 16px',
        borderTop: '1px solid var(--border-light)',
        background: 'rgba(6,182,212,0.04)',
        display: 'flex', alignItems: 'center', gap: 8,
        overflow: 'hidden',
      }}>
        <div style={{
          width: 7, height: 7, borderRadius: '50%', background: 'var(--accent-cyan)',
          boxShadow: '0 0 8px var(--accent-cyan)', animation: 'pulse 2s infinite', flexShrink: 0,
        }} />
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {activity.dependency_mapper.top_cause ?? 'Analysis cycle complete · Next cycle in ~30s'}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: '0.65rem', color: 'var(--text-muted)', flexShrink: 0 }}>
          {activity.cycle_id}
        </span>
      </div>
    </div>
  );
}

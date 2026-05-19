import { useState } from 'react';
import { useAPI } from './hooks/useAPI';
import { useWebSocket } from './hooks/useWebSocket';

import { Header } from './components/Dashboard/Header';
import { MetricCards } from './components/Dashboard/MetricCards';
import { InsightPanel } from './components/Insights/InsightPanel';
import { DependencyGraph } from './components/Graph/DependencyGraph';
import { AnomalyTimeline } from './components/Dashboard/AnomalyTimeline';
import { ForecastPanel } from './components/Dashboard/ForecastPanel';
import { PodGrid } from './components/Dashboard/PodGrid';
import { AgentActivityPanel } from './components/Dashboard/AgentActivityPanel';
import { NLPChat } from './components/Chat/NLPChat';

type TabKey = 'pods' | 'graph' | 'timeline' | 'forecast' | 'agents';

const TABS: { key: TabKey; label: string; emoji: string }[] = [
  { key: 'pods',     label: 'Pod Grid',          emoji: '⬡' },
  { key: 'graph',    label: 'Dependency Graph',   emoji: '⬡' },
  { key: 'timeline', label: 'Anomaly Timeline',   emoji: '⬡' },
  { key: 'forecast', label: 'Forecast Alerts',    emoji: '⬡' },
  { key: 'agents',   label: 'AI Agents',          emoji: '⬡' },
];

function App() {
  const {
    insight, setInsight,
    graph, setGraph,
    health,
    pods, setPods,
    agentActivity, setAgentActivity,
    lastUpdated,
    queryNLP,
  } = useAPI();

  const { isConnected, isDemoMode, lastMessageAt } = useWebSocket(
    setInsight,
    setGraph,
    setPods,
    setAgentActivity,
  );

  const [activeTab, setActiveTab] = useState<TabKey>('pods');

  const displayLastUpdated = lastMessageAt ?? lastUpdated;

  return (
    <div className="dashboard-layout animate-fade-in">
      <Header health={health} />

      <main className="main-area">
        {/* Metric Summary Cards */}
        <MetricCards insight={insight} pods={pods} />

        <div style={{ display: 'flex', gap: '20px', flex: 1, overflow: 'hidden', marginTop: 0 }}>
          {/* ── Main Panel with Tabs ── */}
          <div style={{ flex: 1.6, display: 'flex', flexDirection: 'column', gap: 0, minWidth: 0 }}>

            {/* Tab Bar */}
            <div style={{
              display: 'flex', gap: 0,
              background: 'var(--bg-surface)',
              borderRadius: '12px 12px 0 0',
              border: '1px solid var(--border-light)',
              borderBottom: 'none',
              padding: '4px',
              overflow: 'hidden',
            }}>
              {TABS.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  style={{
                    flex: 1,
                    padding: '9px 12px',
                    border: 'none',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    letterSpacing: '0.02em',
                    transition: 'all 0.2s ease',
                    background: activeTab === tab.key
                      ? 'var(--grad-primary)'
                      : 'transparent',
                    color: activeTab === tab.key
                      ? 'white'
                      : 'var(--text-muted)',
                    boxShadow: activeTab === tab.key
                      ? '0 2px 8px var(--accent-purple-glow)'
                      : 'none',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {tab.label}
                  {/* Live indicator badge for pods and agents */}
                  {(tab.key === 'pods' || tab.key === 'agents') && (
                    <span style={{
                      display: 'inline-block', marginLeft: 5,
                      width: 5, height: 5, borderRadius: '50%',
                      background: isConnected ? 'var(--status-info)' : 'var(--text-muted)',
                      boxShadow: isConnected ? '0 0 5px var(--status-info)' : 'none',
                      verticalAlign: 'middle',
                    }} />
                  )}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <div style={{
              flex: 1,
              borderRadius: '0 0 12px 12px',
              overflow: 'hidden',
              display: 'flex',
            }}>
              {activeTab === 'pods'     && <PodGrid pods={pods} />}
              {activeTab === 'graph'    && <DependencyGraph graph={graph} />}
              {activeTab === 'timeline' && <AnomalyTimeline insight={insight} />}
              {activeTab === 'forecast' && <ForecastPanel insight={insight} />}
              {activeTab === 'agents'   && <AgentActivityPanel activity={agentActivity} />}
            </div>
          </div>

          {/* ── Right Panel — AI Insights ── */}
          <InsightPanel insight={insight} />
        </div>
      </main>

      {/* ── Sidebar ── */}
      <aside className="sidebar-area">
        <NLPChat onQuery={queryNLP} />

        {/* System Status */}
        <div className="glass-panel" style={{ flex: 1, padding: '18px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: isConnected ? 'var(--status-info)' : 'var(--status-critical)', boxShadow: isConnected ? '0 0 6px var(--status-info)' : 'none', display: 'inline-block' }} />
            System Status
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <StatusRow
              label="WebSocket"
              status={isConnected ? 'connected' : 'reconnecting'}
              color={isConnected ? 'var(--status-info)' : 'var(--status-critical)'}
            />
            <StatusRow
              label="Data Mode"
              status={isDemoMode ? 'demo / synthetic' : 'live cluster'}
              color={isDemoMode ? 'var(--status-high)' : 'var(--status-info)'}
            />
            <StatusRow
              label="Analysis Cycle"
              status="every 30s"
              color="var(--accent-purple)"
            />
            <StatusRow
              label="Metrics Refresh"
              status="every 5s"
              color="var(--accent-cyan)"
            />
            <StatusRow
              label="LLM Tier"
              status={health?.llm_tiers_available?.[0]?.split('/')[0] ?? 'detecting…'}
              color={health?.llm_tiers_available?.length ? 'var(--accent-cyan)' : 'var(--text-muted)'}
            />
            <StatusRow
              label="Redis"
              status={health?.redis_connected ? 'connected' : 'unavailable'}
              color={health?.redis_connected ? 'var(--status-info)' : 'var(--status-critical)'}
            />
            {displayLastUpdated && (
              <StatusRow
                label="Last Update"
                status={displayLastUpdated.toLocaleTimeString()}
                color="var(--text-muted)"
              />
            )}
          </div>

          {/* Pods summary */}
          {pods.length > 0 && (
            <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--border-light)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Pod Health</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{pods.length} total</span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {(['healthy','warning','critical'] as const).map(s => {
                  const count = pods.filter(p => p.status === s).length;
                  const color = s === 'critical' ? 'var(--status-critical)' : s === 'warning' ? 'var(--status-high)' : 'var(--status-info)';
                  return (
                    <div key={s} style={{ flex: 1, textAlign: 'center', padding: '6px 4px', borderRadius: 8, background: color + '11', border: `1px solid ${color}33` }}>
                      <div style={{ fontSize: '1rem', fontWeight: 700, color }}>{count}</div>
                      <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>{s}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function StatusRow({ label, status, color }: { label: string; status: string; color: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, boxShadow: `0 0 5px ${color}` }} />
        <span className="mono" style={{ fontSize: '0.73rem', color }}>{status}</span>
      </div>
    </div>
  );
}

export default App;

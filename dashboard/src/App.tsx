import { useState } from 'react';
import { useAPI } from './hooks/useAPI';
import { useWebSocket } from './hooks/useWebSocket';

import { Header } from './components/Dashboard/Header';
import { MetricCards } from './components/Dashboard/MetricCards';
import { InsightPanel } from './components/Insights/InsightPanel';
import { DependencyGraph } from './components/Graph/DependencyGraph';
import { AnomalyTimeline } from './components/Dashboard/AnomalyTimeline';
import { ForecastPanel } from './components/Dashboard/ForecastPanel';
import { NLPChat } from './components/Chat/NLPChat';

type TabKey = 'graph' | 'timeline' | 'forecast';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'graph', label: 'Dependency Graph' },
  { key: 'timeline', label: 'Anomaly Timeline' },
  { key: 'forecast', label: 'Forecast Alerts' },
];

function App() {
  const { insight, graph, health, queryNLP, setInsight, setGraph } = useAPI();
  const { isConnected } = useWebSocket(setInsight, setGraph);
  const [activeTab, setActiveTab] = useState<TabKey>('graph');

  return (
    <div className="dashboard-layout animate-fade-in">
      <Header health={health} />
      
      <main className="main-area">
        <MetricCards insight={insight} />
        
        <div style={{ display: 'flex', gap: '24px', flex: 1, overflow: 'hidden' }}>
          {/* Main Visualizations with Tabs */}
          <div style={{ flex: 1.5, display: 'flex', flexDirection: 'column', gap: '0' }}>
            {/* Tab Bar */}
            <div style={{
              display: 'flex',
              gap: 0,
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
                    padding: '10px 16px',
                    border: 'none',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontSize: '0.82rem',
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
                  }}
                >
                  {tab.label}
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
              {activeTab === 'graph' && <DependencyGraph graph={graph} />}
              {activeTab === 'timeline' && <AnomalyTimeline insight={insight} />}
              {activeTab === 'forecast' && <ForecastPanel insight={insight} />}
            </div>
          </div>
          
          {/* AI Insights */}
          <InsightPanel insight={insight} />
        </div>
      </main>

      <aside className="sidebar-area">
        <NLPChat onQuery={queryNLP} />
        <div className="glass-panel" style={{ flex: 1, padding: '20px' }}>
          <h3 style={{ fontSize: '1rem', marginBottom: '16px' }}>System Status</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <StatusRow
              label="WebSocket"
              status={isConnected ? 'connected' : 'disconnected'}
              color={isConnected ? 'var(--status-info)' : 'var(--status-critical)'}
            />
            <StatusRow
              label="Analysis Cycle"
              status="every 30s"
              color="var(--accent-purple)"
            />
            <StatusRow
              label="LLM Tier"
              status={health?.llm_tiers_available?.[0] ?? 'unavailable'}
              color={health?.llm_tiers_available?.length ? 'var(--accent-cyan)' : 'var(--text-muted)'}
            />
          </div>
        </div>
      </aside>
    </div>
  );
}

function StatusRow({ label, status, color }: { label: string; status: string; color: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: color,
          boxShadow: `0 0 6px ${color}`,
        }} />
        <span className="mono" style={{ fontSize: '0.78rem', color }}>{status}</span>
      </div>
    </div>
  );
}

export default App;

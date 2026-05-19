import { Activity, Server, Cpu, Database } from 'lucide-react';
import type { SystemHealth } from '../../types';

export function Header({ health }: { health: SystemHealth | null }) {
  const isHealthy = health?.status === 'healthy';

  return (
    <header className="header-area glass-panel" style={{ padding: '20px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ 
          background: 'var(--grad-primary)', 
          padding: '10px', 
          borderRadius: '12px',
          display: 'flex',
          boxShadow: '0 4px 12px var(--accent-purple-glow)'
        }}>
          <Activity size={24} color="white" />
        </div>
        <div>
          <h1 className="text-gradient" style={{ fontSize: '1.5rem', marginBottom: '2px' }}>PodMind Intelligence</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontWeight: 500 }}>
            Real-Time Dependency Mapping & Agentic AI
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        <StatusPill icon={<Server size={14} />} label="API" active={true} />
        <StatusPill icon={<Database size={14} />} label="Redis" active={health?.redis_connected ?? false} />
        <StatusPill icon={<Cpu size={14} />} label="LLM" active={!!health?.llm_tiers_available?.length} />
        
        <div style={{ width: '1px', height: '24px', background: 'var(--border-light)', margin: '0 8px' }} />
        
        <div className={`badge ${isHealthy ? 'info' : 'critical'}`} style={{ padding: '6px 12px' }}>
          <div style={{ 
            width: 6, height: 6, borderRadius: '50%', 
            background: 'currentColor',
            boxShadow: isHealthy ? '0 0 8px currentColor' : 'none',
            animation: !isHealthy ? 'pulseGlow 2s infinite' : 'none'
          }} />
          {isHealthy ? 'System Optimal' : 'System Degraded'}
        </div>
      </div>
    </header>
  );
}

function StatusPill({ icon, label, active }: { icon: React.ReactNode, label: string, active: boolean }) {
  return (
    <div style={{ 
      display: 'flex', alignItems: 'center', gap: '6px',
      padding: '6px 12px', borderRadius: '20px',
      background: active ? 'rgba(255,255,255,0.05)' : 'rgba(239, 68, 68, 0.1)',
      color: active ? 'var(--text-secondary)' : 'var(--status-critical)',
      fontSize: '0.8rem', fontWeight: 500,
      border: '1px solid var(--border-light)'
    }}>
      {icon}
      {label}
    </div>
  );
}

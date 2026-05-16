import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User } from 'lucide-react';

interface Message {
  id: string;
  sender: 'user' | 'bot';
  text: string;
}

export function NLPChat({ onQuery }: { onQuery: (q: string) => Promise<string> }) {
  const [messages, setMessages] = useState<Message[]>([
    { id: '0', sender: 'bot', text: 'Ask me anything about the cluster health, active alerts, or resource dependencies.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { id: Date.now().toString(), sender: 'user', text: userMsg }]);
    
    setIsLoading(true);
    const answer = await onQuery(userMsg);
    setIsLoading(false);

    setMessages(prev => [...prev, { id: Date.now().toString(), sender: 'bot', text: answer }]);
  };

  return (
    <div className="glass-panel" style={{ height: '400px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '16px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Bot size={20} color="var(--accent-cyan)" />
        <h3 style={{ fontSize: '1rem' }}>SRE Copilot</h3>
      </div>
      
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {messages.map(m => (
          <div key={m.id} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', flexDirection: m.sender === 'user' ? 'row-reverse' : 'row' }}>
            <div style={{ 
              width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
              background: m.sender === 'user' ? 'var(--accent-blue-glow)' : 'var(--bg-surface-elevated)',
              border: `1px solid ${m.sender === 'user' ? 'var(--accent-blue)' : 'var(--border-light)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              {m.sender === 'user' ? <User size={16} color="var(--accent-blue)" /> : <Bot size={16} color="var(--text-secondary)" />}
            </div>
            <div style={{ 
              background: m.sender === 'user' ? 'var(--accent-blue-glow)' : 'var(--bg-surface)',
              border: `1px solid ${m.sender === 'user' ? 'var(--accent-blue)' : 'var(--border-light)'}`,
              padding: '12px 16px', borderRadius: '16px',
              borderTopRightRadius: m.sender === 'user' ? 4 : 16,
              borderTopLeftRadius: m.sender === 'bot' ? 4 : 16,
              fontSize: '0.9rem', color: 'var(--text-primary)',
              maxWidth: '85%', whiteSpace: 'pre-wrap'
            }}>
              {m.text}
            </div>
          </div>
        ))}
        {isLoading && (
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
             <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--bg-surface-elevated)', border: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={16} color="var(--text-secondary)" />
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Thinking...</div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} style={{ padding: '16px', borderTop: '1px solid var(--border-light)', display: 'flex', gap: '8px' }}>
        <input 
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Query the cluster..."
          style={{ 
            flex: 1, background: 'var(--bg-surface)', border: '1px solid var(--border-light)',
            borderRadius: '24px', padding: '12px 20px', color: 'var(--text-primary)', outline: 'none',
            fontSize: '0.95rem'
          }}
        />
        <button type="submit" disabled={!input.trim() || isLoading} style={{ 
          background: input.trim() ? 'var(--accent-blue)' : 'var(--bg-surface)', 
          border: 'none', borderRadius: '50%', width: 44, height: 44,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: input.trim() ? 'pointer' : 'not-allowed', color: 'white', transition: 'all 0.2s'
        }}>
          <Send size={18} style={{ marginLeft: -2 }} />
        </button>
      </form>
    </div>
  );
}

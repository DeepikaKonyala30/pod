import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, RefreshCw, Zap } from 'lucide-react';

interface Message {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  isError?: boolean;
}

const QUICK_QUERIES = [
  "What's using the most CPU?",
  "Any OOM risks?",
  "Explain dependencies",
  "Top recommendations",
];

export function NLPChat({ onQuery }: { onQuery: (q: string) => Promise<string> }) {
  const [messages, setMessages] = useState<Message[]>([
    { id: '0', sender: 'bot', text: 'Ask me anything about cluster health, active alerts, resource usage, or dependency graphs. I have real-time data.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [lastQuery, setLastQuery] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const sendQuery = async (query: string) => {
    if (!query.trim() || isLoading) return;
    setLastQuery(query);
    setInput('');

    const userMsgId = Date.now().toString();
    setMessages(prev => [...prev, { id: userMsgId, sender: 'user', text: query }]);
    setIsLoading(true);

    try {
      const answer = await onQuery(query);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: answer,
        isError: answer.toLowerCase().includes('unable') || answer.toLowerCase().includes('timed out'),
      }]);
    } catch (err) {
      const errMsg = "Something went wrong. Please try again.";
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'bot',
        text: errMsg,
        isError: true,
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendQuery(input.trim());
  };

  const handleRetry = () => {
    if (lastQuery) sendQuery(lastQuery);
  };

  return (
    <div className="glass-panel" style={{ height: '420px', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-light)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-purple))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 0 12px var(--accent-cyan)44',
        }}>
          <Bot size={16} color="#000" />
        </div>
        <div>
          <h3 style={{ fontSize: '0.9rem', fontWeight: 700 }}>SRE Copilot</h3>
          <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', margin: 0 }}>Powered by Groq · Gemini</p>
        </div>
        <div style={{
          marginLeft: 'auto', width: 7, height: 7, borderRadius: '50%',
          background: 'var(--status-info)',
          boxShadow: '0 0 8px var(--status-info)',
          animation: 'pulse 2s infinite',
        }} />
      </div>

      {/* Messages */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {messages.map(m => (
          <div key={m.id} style={{
            display: 'flex', gap: 8, alignItems: 'flex-start',
            flexDirection: m.sender === 'user' ? 'row-reverse' : 'row',
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
              background: m.sender === 'user'
                ? 'var(--accent-blue-glow)'
                : 'var(--bg-surface-elevated)',
              border: `1px solid ${m.sender === 'user' ? 'var(--accent-blue)' : 'var(--border-light)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {m.sender === 'user'
                ? <User size={13} color="var(--accent-blue)" />
                : <Bot size={13} color="var(--accent-cyan)" />}
            </div>
            <div style={{
              background: m.sender === 'user'
                ? 'var(--accent-blue-glow)'
                : m.isError ? 'rgba(239,68,68,0.08)' : 'var(--bg-surface)',
              border: `1px solid ${m.sender === 'user'
                ? 'var(--accent-blue)'
                : m.isError ? 'rgba(239,68,68,0.3)' : 'var(--border-light)'}`,
              padding: '10px 14px', borderRadius: 14,
              borderTopRightRadius: m.sender === 'user' ? 4 : 14,
              borderTopLeftRadius: m.sender === 'bot' ? 4 : 14,
              fontSize: '0.85rem', color: 'var(--text-primary)',
              maxWidth: '85%', whiteSpace: 'pre-wrap', lineHeight: 1.5,
            }}>
              {m.text}
              {m.isError && (
                <button onClick={handleRetry} style={{
                  display: 'flex', alignItems: 'center', gap: 4, marginTop: 6,
                  background: 'none', border: '1px solid rgba(239,68,68,0.4)',
                  borderRadius: 6, padding: '3px 8px', color: 'var(--status-critical)',
                  cursor: 'pointer', fontSize: '0.75rem',
                }}>
                  <RefreshCw size={11} /> Retry
                </button>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              background: 'var(--bg-surface-elevated)',
              border: '1px solid var(--border-light)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Bot size={13} color="var(--accent-cyan)" />
            </div>
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-light)',
              padding: '10px 16px', borderRadius: 14, borderTopLeftRadius: 4,
              display: 'flex', gap: 5, alignItems: 'center',
            }}>
              {[0, 1, 2].map(i => (
                <div key={i} style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--accent-cyan)',
                  animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
                }} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Quick query chips */}
      <div style={{ padding: '6px 14px', display: 'flex', gap: 5, flexWrap: 'wrap', borderTop: '1px solid var(--border-light)' }}>
        {QUICK_QUERIES.map(q => (
          <button
            key={q}
            onClick={() => sendQuery(q)}
            disabled={isLoading}
            style={{
              padding: '3px 10px', borderRadius: 20,
              background: 'rgba(6,182,212,0.08)',
              border: '1px solid rgba(6,182,212,0.2)',
              color: 'var(--accent-cyan)', fontSize: '0.68rem',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.5 : 1,
              transition: 'all 0.15s',
              display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <Zap size={9} />
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{
        padding: '10px 14px', display: 'flex', gap: 8,
        borderTop: '1px solid var(--border-light)',
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Query the cluster..."
          disabled={isLoading}
          style={{
            flex: 1, background: 'var(--bg-surface)',
            border: '1px solid var(--border-light)',
            borderRadius: 24, padding: '10px 18px',
            color: 'var(--text-primary)', outline: 'none',
            fontSize: '0.88rem', opacity: isLoading ? 0.6 : 1,
            transition: 'border-color 0.2s',
          }}
          onFocus={e => (e.target.style.borderColor = 'var(--accent-cyan)')}
          onBlur={e => (e.target.style.borderColor = 'var(--border-light)')}
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          style={{
            background: input.trim() && !isLoading ? 'var(--accent-cyan)' : 'var(--bg-surface)',
            border: 'none', borderRadius: '50%', width: 40, height: 40,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
            color: input.trim() && !isLoading ? '#000' : 'var(--text-muted)',
            transition: 'all 0.2s', flexShrink: 0,
          }}
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}

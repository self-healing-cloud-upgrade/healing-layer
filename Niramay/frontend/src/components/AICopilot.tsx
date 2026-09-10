/**
 * AICopilot — AI recommendations, feature toggles, and chat interface.
 * Glass panel. Skeuomorphic toggle switches. Severity-colored recommendations.
 * Chat with styled bubbles. All business logic preserved.
 */

import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useTheme, createRipple, type AnomalyLog } from '../designSystem';

export default function AICopilot({ anomalies = [] }: { anomalies?: AnomalyLog[] }) {
  const { isDark } = useTheme();
  const [features, setFeatures] = useState({
    predictive: true,
    rootCause: true,
    smartPriority: false,
  });
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'ai'; text: string }>>([
    { role: 'ai', text: "Llama3 initialized. I'm monitoring your infrastructure for anomalies." },
  ]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const handleSend = () => {
    if (!chatInput.trim()) return;
    const q = chatInput.trim();
    setChatInput('');
    setChatMessages(p => [...p, { role: 'user', text: q }]);
    setTimeout(() => {
      setChatMessages(p => [...p, {
        role: 'ai',
        text: `Analyzing: "${q}". ML models will surface precise insights in the next iteration.`,
      }]);
    }, 1200);
  };

  const sevDot = (s: string): string =>
    s === 'high' ? 'error' : s === 'medium' ? 'warning' : 'neutral';

  const sevBadge = (s: string): string =>
    s === 'high' ? 'badge-error' : s === 'medium' ? 'badge-warning' : 'badge-neutral';

  return (
    <div id="ai-copilot" className="glass card-glass" style={{
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-5) var(--space-6) var(--space-3)',
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-md)',
          color: 'var(--color-text-primary)',
        }}>
          AI Copilot
        </span>
        <span className="badge badge-neutral" style={{
          background: 'var(--color-accent-tertiary)',
          color: 'var(--color-accent-primary)',
        }}>
          Preview
        </span>
      </div>

      <div className="scroll-fade" style={{
        flex: 1,
        padding: 'var(--space-2) var(--space-6) var(--space-6)',
        maxHeight: 480,
        overflowY: 'auto',
      }}>

        {/* ── Feature Toggles ── */}
        <div style={{ marginBottom: 'var(--space-8)' }}>
          <div style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--font-weight-medium)' as any,
            letterSpacing: 'var(--tracking-widest)',
            textTransform: 'uppercase',
            color: 'var(--color-text-tertiary)',
            marginBottom: 'var(--space-4)',
          }}>
            Features
          </div>
          {([
            { key: 'predictive' as const, label: 'Predictive Healing' },
            { key: 'rootCause' as const, label: 'Root Cause Analysis' },
            { key: 'smartPriority' as const, label: 'Smart Prioritization' },
          ]).map(f => (
            <div key={f.key} style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 'var(--space-3) 0',
              borderBottom: '1px solid var(--color-border-subtle)',
            }}>
              <span style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text-primary)',
              }}>{f.label}</span>

              {/* Skeuomorphic toggle */}
              <button
                role="switch"
                aria-checked={features[f.key]}
                aria-label={`Toggle ${f.label}`}
                onClick={() => setFeatures(x => ({ ...x, [f.key]: !x[f.key] }))}
                style={{
                  width: 40,
                  height: 22,
                  borderRadius: 'var(--radius-full)',
                  padding: 2,
                  cursor: 'pointer',
                  border: 'none',
                  flexShrink: 0,
                  background: features[f.key]
                    ? 'linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-secondary))'
                    : isDark
                      ? 'rgba(255, 248, 235, 0.08)'
                      : 'rgba(28, 24, 18, 0.08)',
                  boxShadow: features[f.key]
                    ? '0 2px 8px rgba(196, 101, 58, 0.25), inset 0 1px 0 rgba(255,255,255,0.15)'
                    : isDark
                      ? 'inset 2px 2px 4px rgba(0,0,0,0.3), inset -1px -1px 2px rgba(255,255,255,0.03)'
                      : 'inset 2px 2px 4px rgba(174, 168, 157, 0.3), inset -2px -2px 4px rgba(255,255,255,0.6)',
                  transition: 'background 250ms var(--ease-out-expo), box-shadow 250ms var(--ease-out-expo)',
                }}
              >
                <span style={{
                  display: 'block',
                  width: 18,
                  height: 18,
                  borderRadius: '50%',
                  background: features[f.key]
                    ? '#fff'
                    : isDark
                      ? 'rgba(240, 235, 227, 0.3)'
                      : 'rgba(28, 24, 18, 0.15)',
                  transform: `translateX(${features[f.key] ? 18 : 0}px)`,
                  transition: 'transform 400ms cubic-bezier(0.34, 1.56, 0.64, 1), background 250ms ease',
                  boxShadow: features[f.key]
                    ? '0 1px 4px rgba(0,0,0,0.15)'
                    : 'none',
                }} />
              </button>
            </div>
          ))}
        </div>

        {/* ── Recommendations (AI RCA) ── */}
        <div style={{ marginBottom: 'var(--space-8)' }}>
          <div style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--font-weight-medium)' as any,
            letterSpacing: 'var(--tracking-widest)',
            textTransform: 'uppercase',
            color: 'var(--color-text-tertiary)',
            marginBottom: 'var(--space-4)',
          }}>
            AI RCA (Ollama)
          </div>
          {anomalies.filter(a => a.ai_analysis).slice(0, 5).map(a => {
            const ai = a.ai_analysis!;
            return (
            <motion.div
              key={a.detection_id}
              className="row-interactive"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              style={{
                padding: 'var(--space-3) var(--space-2)',
                marginBottom: 'var(--space-1)',
                cursor: 'default',
              }}
            >
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                marginBottom: 'var(--space-1)',
              }}>
                <span className={`dot dot-${ai.confidence > 0.8 ? 'success' : 'warning'}`} />
                <span className={`badge ${ai.confidence > 0.8 ? 'badge-success' : 'badge-warning'}`}>
                  {Math.round(ai.confidence * 100)}% Conf
                </span>
                <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                  {a.endpoint}
                </span>
              </div>

              <div style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text-primary)',
                lineHeight: 'var(--leading-normal)',
                paddingLeft: 'var(--space-4)',
              }}>
                {ai.root_cause}
              </div>

              {/* Progressive disclosure */}
              <div className="reveal-on-hover" style={{ paddingLeft: 'var(--space-4)', marginTop: 'var(--space-2)' }}>
                <div style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-text-tertiary)',
                  lineHeight: 'var(--leading-normal)',
                  marginBottom: 'var(--space-2)',
                }}>
                  LLM Suggestion: Apply {ai.suggested_action} to mitigate further degradation.
                </div>
                <button
                  className="btn-ghost ripple-host"
                  onClick={(e) => createRipple(e)}
                  style={{
                    padding: '5px 14px',
                    fontSize: 'var(--text-xs)',
                  }}
                >
                  Execute {ai.suggested_action}
                </button>
              </div>
            </motion.div>
            );
          })}
          {anomalies.filter(a => a.ai_analysis).length === 0 && (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', paddingLeft: 'var(--space-4)' }}>
              No critical RCA reports at this time.
            </div>
          )}
        </div>

        {/* ── Chat ── */}
        <div>
          <div style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--font-weight-medium)' as any,
            letterSpacing: 'var(--tracking-widest)',
            textTransform: 'uppercase',
            color: 'var(--color-text-tertiary)',
            marginBottom: 'var(--space-4)',
          }}>
            Converse
          </div>

          {/* Messages */}
          <div style={{
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-3)',
            maxHeight: 160,
            overflowY: 'auto',
            background: 'var(--color-bg-sunken)',
            border: '1px solid var(--color-border-subtle)',
            marginBottom: 'var(--space-3)',
          }}>
            {chatMessages.map((m, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 'var(--space-2)',
              }}>
                <div style={{
                  maxWidth: '82%',
                  padding: 'var(--space-2) var(--space-3)',
                  borderRadius: m.role === 'user'
                    ? 'var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg)'
                    : 'var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--radius-sm)',
                  background: m.role === 'user'
                    ? 'var(--color-accent-tertiary)'
                    : 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border-subtle)',
                  fontSize: 'var(--text-xs)',
                  lineHeight: 'var(--leading-normal)',
                  color: m.role === 'user' ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)',
                }}>
                  {m.text}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <input
              id="copilot-chat-input"
              type="text"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder="Ask about system health…"
              className="input"
              style={{
                flex: 1,
                height: 40,
                padding: '0 var(--space-4)',
                fontSize: 'var(--text-sm)',
                borderRadius: 'var(--radius-md)',
              }}
            />
            <button
              id="copilot-send-btn"
              onClick={handleSend}
              className="btn-primary ripple-host"
              onMouseDown={(e) => createRipple(e)}
              style={{
                height: 40,
                padding: '0 var(--space-5)',
                fontSize: 'var(--text-xs)',
                borderRadius: 'var(--radius-md)',
              }}
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

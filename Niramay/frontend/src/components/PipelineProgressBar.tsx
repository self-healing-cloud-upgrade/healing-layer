/**
 * PipelineProgressBar — Feature 4.
 *
 * Compact 5-node progress bar above the main dashboard panels.
 * Subscribes to pipeline stage via usePipelineEvents (2s poll).
 * Shows a live accessible event feed (last 8 events).
 * "Current Stage" chip in top-right.
 *
 * Node states: idle | active (pulse) | completed (✓) | failed (✕)
 */

import { usePipelineEvents } from '../hooks/usePipelineEvents';
import type { NodeState } from '../hooks/usePipelineEvents';
import type { PipelineEvent } from '../designSystem';

const PIPELINE_NODES = ['Ingestion', 'Detection', 'Analysis', 'Healing', 'Verification'];

function NodeIcon({ state }: { state: NodeState }) {
  const size = 28;
  const baseStyle: React.CSSProperties = {
    width: size, height: size, borderRadius: '50%', flexShrink: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    transition: 'all 300ms',
  };

  if (state === 'completed') return (
    <div style={{ ...baseStyle, background: 'var(--color-status-success)', border: '2px solid var(--color-status-success)' }}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
        <polyline points="2,6 5,9 10,3" />
      </svg>
    </div>
  );
  if (state === 'failed') return (
    <div style={{ ...baseStyle, background: 'var(--color-status-error)', border: '2px solid var(--color-status-error)' }}>
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
        <line x1="2" y1="2" x2="8" y2="8" /><line x1="8" y1="2" x2="2" y2="8" />
      </svg>
    </div>
  );
  if (state === 'active') return (
    <div style={{
      ...baseStyle, background: 'var(--color-accent-primary)',
      border: '2px solid var(--color-accent-primary)',
      animation: 'niramayPulse 1.4s ease-in-out infinite',
    }} />
  );
  return (
    <div style={{ ...baseStyle, background: 'transparent', border: '2px solid var(--color-border-default)' }} />
  );
}

function eventColor(ev: PipelineEvent): string {
  if (ev.event_type?.includes('failed') || ev.event_type?.includes('error')) return 'var(--color-status-error)';
  if (ev.event_type?.includes('ended') || ev.event_type?.includes('complete')) return 'var(--color-status-success)';
  return 'var(--color-text-tertiary)';
}

function formatEventTime(ts: string): string {
  try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch { return ts; }
}

export default function PipelineProgressBar() {
  const { events, currentStageLabel, nodeStates } = usePipelineEvents(true);

  return (
    <div style={{
      background: 'var(--color-bg-secondary)',
      border: '1px solid var(--color-border-subtle)',
      borderRadius: 'var(--radius-lg)',
      padding: 'var(--space-5) var(--space-6)',
      marginBottom: 'var(--space-8)',
    }}
      role="status"
      aria-label="Pipeline stage progress"
    >
      {/* Top row: label + current stage chip */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase' }}>
          Pipeline
        </span>
        <span style={{
          fontSize: 10, padding: '2px 10px',
          borderRadius: 'var(--radius-full)',
          background: currentStageLabel === 'Idle'
            ? 'var(--color-accent-tertiary)'
            : 'rgba(212,132,94,0.1)',
          border: `1px solid ${currentStageLabel === 'Idle' ? 'var(--color-border-subtle)' : 'rgba(212,132,94,0.25)'}`,
          color: currentStageLabel === 'Idle' ? 'var(--color-text-tertiary)' : 'var(--color-accent-primary)',
          fontWeight: 600,
          letterSpacing: 'var(--tracking-wider)',
        }}>
          {currentStageLabel}
        </span>
      </div>

      {/* Node bar */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
        {nodeStates.map((node, idx) => (
          <div key={node.label} style={{ display: 'flex', alignItems: 'center', flex: idx < PIPELINE_NODES.length - 1 ? 1 : undefined }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <NodeIcon state={node.state} />
              <span style={{
                fontSize: 10, whiteSpace: 'nowrap',
                color: node.state !== 'idle' ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
                fontWeight: node.state === 'active' ? 600 : 400,
                letterSpacing: 'var(--tracking-wider)',
                textTransform: 'uppercase',
                transition: 'color 300ms',
              }}>
                {node.label}
              </span>
            </div>
            {idx < PIPELINE_NODES.length - 1 && (
              <div style={{
                flex: 1,
                height: 1,
                marginBottom: 14,
                background: node.state === 'completed' ? 'var(--color-status-success)' : 'var(--color-border-subtle)',
                transition: 'background 300ms',
              }} />
            )}
          </div>
        ))}
      </div>

      {/* Live event feed */}
      <ol
        aria-live="polite"
        aria-label="Pipeline events"
        style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 2 }}
      >
        {events.length === 0 ? (
          <li style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', fontStyle: 'italic' }}>
            No events yet — waiting for pipeline activity.
          </li>
        ) : (
          events.slice(0, 8).map((ev, i) => (
            <li key={`${ev.timestamp}-${i}`} style={{
              fontSize: 'var(--text-xs)',
              color: eventColor(ev),
              fontFamily: 'var(--font-mono)',
              lineHeight: 'var(--leading-normal)',
            }}>
              <span style={{ color: 'var(--color-text-tertiary)', marginRight: 8 }}>{formatEventTime(ev.timestamp)}</span>
              {ev.message || `${ev.event_type} — ${ev.stage}`}
            </li>
          ))
        )}
      </ol>

      <style>{`
        @keyframes niramayPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.55; transform: scale(1.25); }
        }
      `}</style>
    </div>
  );
}

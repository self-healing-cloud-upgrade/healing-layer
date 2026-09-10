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

import { useState, useEffect, useRef } from 'react';
import { usePipelineEvents } from '../hooks/usePipelineEvents';
import type { NodeState } from '../hooks/usePipelineEvents';
import type { PipelineEvent } from '../designSystem';

// Mirror of backend SETTLING_WINDOWS in verification_worker.py
const SETTLING_WINDOWS: Record<string, number> = {
  restart_service:      45,
  throttle_requests:    15,
  flush_cache:          10,
  scale_up:             30,
  circuit_breaker:      20,
  rollback_deployment:  60,
  escalate_only:         0,
  none:                  0,
};
const DEFAULT_SETTLING_WINDOW = 15;

// Mirror of COOLDOWN_DURATION_SECONDS in dispatcher/worker.py
const COOLDOWN_DURATION_S = 90;

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

/** Seconds remaining for the current timed stage, or null if not applicable. */
function computeRemaining(
  currentStage: string | null,
  stageTimestamp: string | null,
  stageHealingAction: string | null,
): { remaining: number; total: number; forNode: 'Healing' | 'Verification' } | null {
  if (!stageTimestamp) return null;

  const elapsed = (Date.now() - new Date(stageTimestamp).getTime()) / 1000;

  if (currentStage === 'stage_5_cooldown') {
    return {
      remaining: Math.max(0, Math.ceil(COOLDOWN_DURATION_S - elapsed)),
      total: COOLDOWN_DURATION_S,
      forNode: 'Healing',
    };
  }

  if (currentStage === 'stage_6_verification_running') {
    const total = SETTLING_WINDOWS[stageHealingAction ?? ''] ?? DEFAULT_SETTLING_WINDOW;
    return {
      remaining: Math.max(0, Math.ceil(total - elapsed)),
      total,
      forNode: 'Verification',
    };
  }

  return null;
}

export default function PipelineProgressBar() {
  const { events, currentStage, currentStageLabel, nodeStates, stageTimestamp, stageHealingAction, refetch } =
    usePipelineEvents(true);
  const [eventsExpanded, setEventsExpanded] = useState(false);

  // Tick every second so we recompute remaining time without storing it in state
  const [, setTick] = useState(0);
  const tickRef = useRef<ReturnType<typeof setInterval>>();
  // Track previous remaining to detect the 0-crossing and trigger an immediate refetch
  const prevRemainingRef = useRef<number | null>(null);

  const isTimedStage =
    currentStage === 'stage_5_cooldown' || currentStage === 'stage_6_verification_running';

  useEffect(() => {
    if (isTimedStage && stageTimestamp) {
      tickRef.current = setInterval(() => setTick(t => t + 1), 1000);
    } else {
      clearInterval(tickRef.current);
      prevRemainingRef.current = null;
    }
    return () => clearInterval(tickRef.current);
  }, [isTimedStage, stageTimestamp]);

  const timerInfo = computeRemaining(currentStage, stageTimestamp, stageHealingAction);

  // The moment the countdown crosses from 1→0, trigger an immediate backend poll
  // so confirmation arrives as fast as possible instead of waiting up to 1s more.
  const currentRemaining = timerInfo?.remaining ?? null;
  if (prevRemainingRef.current !== null && prevRemainingRef.current > 0 && currentRemaining === 0) {
    refetch();
  }
  prevRemainingRef.current = currentRemaining;

  return (
    <div
      style={{
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
          background: currentStageLabel === 'Waiting'
            ? 'var(--color-accent-tertiary)'
            : 'rgba(212,132,94,0.1)',
          border: `1px solid ${currentStageLabel === 'Waiting' ? 'var(--color-border-subtle)' : 'rgba(212,132,94,0.25)'}`,
          color: currentStageLabel === 'Waiting' ? 'var(--color-text-tertiary)' : 'var(--color-accent-primary)',
          fontWeight: 600,
          letterSpacing: 'var(--tracking-wider)',
        }}>
          {currentStageLabel}
        </span>
      </div>

      {/* Node bar */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
        {nodeStates.map((node, idx) => {
          const isTimerNode = timerInfo?.forNode === node.label;
          const remaining = isTimerNode ? timerInfo!.remaining : null;

          // Sub-label priority: active timer → completed timestamp
          const subLabel = (() => {
            if (isTimerNode && remaining !== null) {
              if (remaining === 0) {
                return (
                  <span style={{
                    fontSize: 9, whiteSpace: 'nowrap',
                    color: 'var(--color-status-info)',
                    fontFamily: 'var(--font-mono)',
                    marginTop: -2,
                    animation: 'niramayPulse 1.2s ease-in-out infinite',
                  }}>
                    confirming…
                  </span>
                );
              }
              const color = node.label === 'Healing'
                ? 'var(--color-status-info)'
                : 'var(--color-status-warning)';
              return (
                <span style={{
                  fontSize: 9, whiteSpace: 'nowrap',
                  color,
                  fontFamily: 'var(--font-mono)',
                  fontVariantNumeric: 'tabular-nums',
                  marginTop: -2,
                }}>
                  {remaining}s remaining
                </span>
              );
            }
            if (node.timestamp) {
              return (
                <span style={{
                  fontSize: 9, whiteSpace: 'nowrap',
                  color: 'var(--color-text-tertiary)',
                  fontFamily: 'var(--font-mono)',
                  marginTop: -2,
                }}>
                  {formatEventTime(node.timestamp)}
                </span>
              );
            }
            return null;
          })();

          return (
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
                {subLabel}
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
          );
        })}
      </div>

      {/* Live event feed — collapsible */}
      <button
        onClick={() => setEventsExpanded(v => !v)}
        aria-expanded={eventsExpanded}
        aria-controls="pipeline-events-list"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: 'none',
          border: 'none',
          padding: '2px 0',
          cursor: 'pointer',
          color: 'var(--color-text-tertiary)',
          fontSize: 10,
          letterSpacing: 'var(--tracking-wider)',
          textTransform: 'uppercase',
          marginBottom: eventsExpanded ? 'var(--space-2)' : 0,
        }}
      >
        <svg
          width="10" height="10" viewBox="0 0 10 10" fill="none"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
          style={{ transition: 'transform 200ms', transform: eventsExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
        >
          <path d="M2 3.5l3 3 3-3" />
        </svg>
        Events {events.length > 0 ? `(${Math.min(events.length, 8)})` : ''}
      </button>

      {eventsExpanded && (
        <ol
          id="pipeline-events-list"
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
      )}

      <style>{`
        @keyframes niramayPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.55; transform: scale(1.25); }
        }
      `}</style>
    </div>
  );
}

/**
 * LiveVisualizer — Page 2: The Live Operations Dashboard.
 * Shows the Input → Processing → Output pipeline in real-time.
 */

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Navbar from '../components/layout/Navbar';
import PipelineProgressBar from '../components/PipelineProgressBar';
import { useNiramayData } from '../hooks/useNiramayData';
import { useTheme, statusDotClass, timeAgo, createRipple } from '../designSystem';

/* ═══════════════════════════════════════════════════════════════════
   METRICS BAR
   ═══════════════════════════════════════════════════════════════════ */

function MetricsBar({ metrics, isLive, setIsLive, lastRefresh, fetchData }: {
  metrics: ReturnType<typeof useNiramayData>['metrics'];
  isLive: boolean;
  setIsLive: (v: boolean) => void;
  lastRefresh: Date;
  fetchData: () => void;
}) {
  const { isDark } = useTheme();
  const items = [
    { label: 'Requests', value: metrics.totalRequests, color: 'var(--color-text-primary)' },
    { label: 'Success', value: `${metrics.successRate}%`, color: 'var(--color-status-success)' },
    { label: 'Latency', value: `${metrics.avgLatency}`, color: 'var(--color-text-primary)' },
    { label: 'Anomalies', value: metrics.activeAnomalies, color: metrics.activeAnomalies > 0 ? 'var(--color-status-warning)' : 'var(--color-text-primary)' },
    { label: 'Healed', value: metrics.totalHealed, color: metrics.totalHealed > 0 ? 'var(--color-status-success)' : 'var(--color-text-primary)' },
  ];

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-3)',
      padding: 'var(--space-3) var(--space-4)',
      background: 'var(--color-bg-elevated)',
      borderRadius: 'var(--radius-xl)',
      border: '1px solid var(--color-border-subtle)',
      flexWrap: 'wrap',
    }}>
      {/* Live toggle */}
      <button
        onClick={() => setIsLive(!isLive)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: '4px 14px',
          borderRadius: 'var(--radius-full)',
          background: isLive ? 'var(--color-accent-tertiary)' : 'var(--color-bg-sunken)',
          border: '1px solid ' + (isLive ? 'var(--color-border-default)' : 'var(--color-border-subtle)'),
          cursor: 'pointer',
        }}
      >
        <span className={`dot ${isLive ? 'dot-success dot-live' : 'dot-neutral'}`} style={{ width: 6, height: 6 }} />
        <span style={{
          fontSize: 10,
          color: isLive ? 'var(--color-status-success)' : 'var(--color-text-tertiary)',
          letterSpacing: 'var(--tracking-widest)',
          textTransform: 'uppercase',
          fontWeight: 'var(--font-weight-medium)' as any,
        }}>
          {isLive ? 'Live' : 'Paused'}
        </span>
      </button>

      <div style={{ width: 1, height: 24, background: 'var(--color-border-subtle)' }} />

      {/* Metrics */}
      {items.map(item => (
        <div key={item.label} style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '0 var(--space-3)',
          minWidth: 70,
        }}>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-lg)',
            fontWeight: 'var(--font-weight-bold)',
            color: item.color,
            fontVariantNumeric: 'tabular-nums',
            lineHeight: 1,
          }}>
            {item.value}
          </span>
          <span style={{
            fontSize: 9,
            color: 'var(--color-text-tertiary)',
            letterSpacing: 'var(--tracking-widest)',
            textTransform: 'uppercase',
            marginTop: 2,
          }}>
            {item.label}
          </span>
        </div>
      ))}

      <div style={{ flex: 1 }} />

      {/* Refresh + timestamp */}
      <button onClick={fetchData} className="btn-icon" aria-label="Refresh data" style={{ width: 30, height: 30 }}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
          <path d="M1.5 8a6.5 6.5 0 0 1 12-3" /><path d="M14.5 8a6.5 6.5 0 0 1-12 3" />
          <polyline points="1.5,3 1.5,7 5,6" /><polyline points="14.5,13 14.5,9 11,10" />
        </svg>
      </button>
      <span style={{
        fontSize: 10,
        color: 'var(--color-text-tertiary)',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   STAGE 1: OBSERVATION STREAM
   ═══════════════════════════════════════════════════════════════════ */

function ObservationStream({ logs }: { logs: ReturnType<typeof useNiramayData>['logs'] }) {
  const { isDark } = useTheme();
  const seenRef = useRef<Set<string>>(new Set());
  return (
    <div className="glow-card" style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      minHeight: 460,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-4) var(--space-5)',
        borderBottom: '1px solid var(--color-border-subtle)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--color-status-info)" strokeWidth="1.5" strokeLinecap="round">
            <circle cx="8" cy="8" r="6" /><circle cx="8" cy="8" r="2" />
          </svg>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--color-text-primary)',
          }}>
            Observation Stream
          </span>
        </div>
        <span className="badge badge-info" style={{ fontSize: 10 }}>{logs.length} events</span>
      </div>

      <div style={{
        fontSize: 'var(--text-xs)',
        color: 'var(--color-text-tertiary)',
        padding: 'var(--space-2) var(--space-5)',
        borderBottom: '1px solid var(--color-border-subtle)',
        fontFamily: 'var(--font-mono)',
        letterSpacing: 'var(--tracking-wider)',
        textTransform: 'uppercase',
      }}>
        Incoming API Traffic
      </div>

      {/* Log feed */}
      <div className="scroll-fade" style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--space-2) var(--space-3)',
        maxHeight: 380,
      }}>
        <AnimatePresence initial={false}>
          {logs.slice(0, 25).map((log, i) => {
            const lk = log.request_id || `${log.timestamp}-${i}`;
            const isNew = !seenRef.current.has(lk);
            if (isNew) seenRef.current.add(lk);
            if (seenRef.current.size > 100) seenRef.current = new Set(Array.from(seenRef.current).slice(-50));
            return (
            <motion.div
              key={lk}
              initial={isNew ? { opacity: 0, x: -20 } : false}
              animate={{ opacity: 1, x: 0 }}
              transition={isNew ? { duration: 0.25, delay: Math.min(i * 0.02, 0.2) } : { duration: 0 }}
              className="row-interactive"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: 'var(--space-2) var(--space-2)',
                fontSize: 'var(--text-xs)',
              }}
            >
              <span className={`dot dot-${statusDotClass(log.status_code)}`} />
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontWeight: 'var(--font-weight-medium)' as any,
                color: 'var(--color-text-secondary)',
                width: 32,
                flexShrink: 0,
                letterSpacing: 'var(--tracking-wider)',
              }}>
                {log.method}
              </span>
              <span style={{
                flex: 1,
                color: 'var(--color-text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
              }} title={log.endpoint}>
                {log.endpoint.replace('/api/v1/', '/')}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)',
                color: `var(--color-status-${statusDotClass(log.status_code)})`,
                fontVariantNumeric: 'tabular-nums',
                fontWeight: 'var(--font-weight-medium)' as any,
              }}>
                {log.status_code}
              </span>
              <span className="subtle-on-hover" style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--color-text-tertiary)',
                width: 40,
                textAlign: 'right',
              }}>
                {(log.response_time_ms ?? 0).toFixed(0)}ms
              </span>
            </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   STAGE 2: DETECTION ENGINE
   ═══════════════════════════════════════════════════════════════════ */

function DetectionEngine({ anomalies, stats }: { anomalies: any[], stats: any }) {
  const { isDark } = useTheme();
  const hasAnomalies = anomalies.length > 0;
  const seenRef = useRef<Set<string>>(new Set());

  return (
    <div className="glow-card" style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      minHeight: 460,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-4) var(--space-5)',
        borderBottom: '1px solid var(--color-border-subtle)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--color-status-warning)" strokeWidth="1.5" strokeLinecap="round">
            <path d="M8 2L14 6V14H2V6L8 2Z" /><path d="M8 7v3" /><circle cx="8" cy="12" r="0.5" fill="var(--color-status-warning)" />
          </svg>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--color-text-primary)',
          }}>
            Detection Engine
          </span>
        </div>
        {hasAnomalies && (
          <span className="badge badge-warning" style={{ fontSize: 10 }}>
            {anomalies.length} detected
          </span>
        )}
      </div>

      {/* AI Core Visualization */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-6)',
        position: 'relative',
      }}>
        {/* Pulse rings */}
        <div className="pulse-core" style={{
          width: 80,
          height: 80,
          borderRadius: '50%',
          background: hasAnomalies
            ? (isDark
              ? 'radial-gradient(circle, rgba(255, 140, 66, 0.15) 0%, rgba(255, 140, 66, 0.02) 70%)'
              : 'radial-gradient(circle, rgba(245, 158, 11, 0.12) 0%, rgba(245, 158, 11, 0.02) 70%)')
            : (isDark
              ? 'radial-gradient(circle, rgba(0, 255, 136, 0.12) 0%, rgba(0, 255, 136, 0.02) 70%)'
              : 'radial-gradient(circle, rgba(16, 185, 129, 0.12) 0%, rgba(16, 185, 129, 0.02) 70%)'),
          border: `2px solid ${hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.5s ease',
          ...(isDark ? {
            boxShadow: `0 0 20px ${hasAnomalies ? 'var(--glow-warning)' : 'var(--glow-primary)'}`,
          } : {}),
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)'} strokeWidth="1.5">
            <path d="M12 4L20 8V16L12 20L4 16V8L12 4Z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </div>

        {/* Status label */}
        <div style={{
          position: 'absolute',
          bottom: 'var(--space-2)',
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)',
          letterSpacing: 'var(--tracking-widest)',
          textTransform: 'uppercase',
        }}>
          {hasAnomalies ? 'ANOMALIES DETECTED' : 'MONITORING'}
        </div>
      </div>

      {/* Anomaly feed */}
      <div className="scroll-fade" style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--space-2) var(--space-3)',
        maxHeight: 260,
      }}>
        {anomalies.slice(0, 15).map((a, i) => {
          const ak = a.detection_id || `${a.timestamp}-${i}`;
          const isNew = !seenRef.current.has(ak);
          if (isNew) seenRef.current.add(ak);
          if (seenRef.current.size > 100) seenRef.current = new Set(Array.from(seenRef.current).slice(-50));
          return (
          <motion.div
            key={ak}
            initial={isNew ? { opacity: 0, y: 8 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={isNew ? { duration: 0.25, delay: Math.min(i * 0.03, 0.3) } : { duration: 0 }}
            className="row-interactive"
            style={{
              padding: 'var(--space-2)',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
            }}>
              <span className={`dot dot-${a.severity === 'critical' || a.severity === 'high' ? 'error' : 'warning'}`} />
              <span style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: a.severity === 'critical' || a.severity === 'high' ? 'var(--color-status-error)' : 'var(--color-status-warning)',
                fontVariantNumeric: 'tabular-nums',
              }}>
                {a.anomaly_score.toFixed(2)}
              </span>
              <span style={{
                flex: 1,
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontFamily: 'var(--font-mono)',
              }}>
                {a.endpoint.replace('/api/v1/', '/')}
              </span>
              <span style={{
                fontSize: 9,
                color: 'var(--color-text-tertiary)',
              }}>
                {timeAgo(a.timestamp)}
              </span>
            </div>
            {a.anomaly_reasons.length > 0 && (
              <div className="reveal-on-hover" style={{
                display: 'flex',
                gap: 'var(--space-1)',
                paddingLeft: 'var(--space-4)',
                flexWrap: 'wrap',
              }}>
                {a.anomaly_reasons.map((r: string, ri: number) => (
                  <span key={ri} className="badge badge-neutral" style={{ fontSize: 9, padding: '0 6px' }}>
                    {r.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </motion.div>
          );
        })}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   STAGE 3: HEALING OUTPUT
   ═══════════════════════════════════════════════════════════════════ */

/**
 * True outcome of a healing action.
 *
 * verification_status is the definitive signal — it reflects what the
 * verification worker observed after the settling window. An action can have
 * status='failed' (the restart call itself failed) yet verification_status='HEALED'
 * (system recovered anyway). We return 'pending' when the action failed but
 * verification hasn't completed yet, to avoid showing "Failed" prematurely.
 */
function effectiveOutcome(a: { status?: string; verification_status?: string }): 'success' | 'failed' | 'pending' {
  if (a.verification_status === 'HEALED' || a.verification_status === 'SUCCESS') return 'success';
  if (a.verification_status === 'FAILED' || a.verification_status === 'ESCALATED') return 'failed';
  if (a.status === 'success') return 'success';
  // status='failed' with no verification_status = action failed but verification
  // hasn't run yet — show as neutral "Verifying" to avoid premature failure display.
  return 'pending';
}

function HealingOutput({ actions }: { actions: ReturnType<typeof useNiramayData>['healingActions'] }) {
  const { isDark } = useTheme();
  const seenRef = useRef<Set<string>>(new Set());
  // Only show actual healing outcomes — filter out batched/suppressed/skipped records
  const visibleActions = actions.filter(a => a.status === 'success' || a.status === 'failed');
  return (
    <div className="glow-card" style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      minHeight: 460,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-4) var(--space-5)',
        borderBottom: '1px solid var(--color-border-subtle)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--color-status-success)" strokeWidth="1.5" strokeLinecap="round">
            <path d="M4 8l3 3 5-6" /><circle cx="8" cy="8" r="6" />
          </svg>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--color-text-primary)',
          }}>
            Autonomous Healing
          </span>
        </div>
        {visibleActions.filter(a => effectiveOutcome(a) === 'success').length > 0 && (
          <span className="badge badge-success" style={{ fontSize: 10 }}>
            {visibleActions.filter(a => effectiveOutcome(a) === 'success').length} healed
          </span>
        )}
        {visibleActions.filter(a => effectiveOutcome(a) === 'pending').length > 0 && (
          <span className="badge badge-warning" style={{ fontSize: 10 }}>
            {visibleActions.filter(a => effectiveOutcome(a) === 'pending').length} verifying
          </span>
        )}
        {visibleActions.filter(a => effectiveOutcome(a) === 'failed').length > 0 && (
          <span className="badge badge-error" style={{ fontSize: 10 }}>
            {visibleActions.filter(a => effectiveOutcome(a) === 'failed').length} failed
          </span>
        )}
      </div>

      <div style={{
        fontSize: 'var(--text-xs)',
        color: 'var(--color-text-tertiary)',
        padding: 'var(--space-2) var(--space-5)',
        borderBottom: '1px solid var(--color-border-subtle)',
        fontFamily: 'var(--font-mono)',
        letterSpacing: 'var(--tracking-wider)',
        textTransform: 'uppercase',
      }}>
        Healing Action Log
      </div>

      {/* Action feed */}
      <div className="scroll-fade" style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--space-2) var(--space-3)',
        maxHeight: 380,
      }}>
        <AnimatePresence initial={false}>
          {visibleActions.slice(0, 20).map((action, i) => {
            const hk = action.alert_id || `${action.timestamp}-${i}`;
            const isNew = !seenRef.current.has(hk);
            if (isNew) seenRef.current.add(hk);
            if (seenRef.current.size > 100) seenRef.current = new Set(Array.from(seenRef.current).slice(-50));
            return (
            <motion.div
              key={hk}
              initial={isNew ? { opacity: 0, x: 20 } : false}
              animate={{ opacity: 1, x: 0 }}
              transition={isNew ? { duration: 0.25, delay: Math.min(i * 0.03, 0.3) } : { duration: 0 }}
              className="row-interactive"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                padding: 'var(--space-2)',
              }}
            >
              {/* Icon — driven by verification_status (ground truth), fallback to status */}
              {(() => {
                const outcome = effectiveOutcome(action);
                const iconBg =
                  outcome === 'success' ? 'rgba(0,255,136,0.08)' :
                  outcome === 'pending' ? 'rgba(245,158,11,0.08)' :
                  'rgba(255,60,60,0.08)';
                return (
                  <div style={{
                    width: 26, height: 26,
                    borderRadius: 'var(--radius-md)',
                    background: iconBg,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    {outcome === 'success' && (
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="var(--color-status-success)" strokeWidth="1.5" strokeLinecap="round">
                        <path d="M4 8l3 3 5-6" /><circle cx="8" cy="8" r="6" />
                      </svg>
                    )}
                    {outcome === 'pending' && (
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="var(--color-status-warning)" strokeWidth="1.5" strokeLinecap="round">
                        <circle cx="8" cy="8" r="6" /><path d="M8 5v3.5l2 2" />
                      </svg>
                    )}
                    {outcome === 'failed' && (
                      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="var(--color-status-error)" strokeWidth="1.5" strokeLinecap="round">
                        <path d="M4 4l8 8M12 4l-8 8" /><circle cx="8" cy="8" r="6" />
                      </svg>
                    )}
                  </div>
                );
              })()}

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}>
                  {action.healing_action.replace(/_/g, ' ')}
                </div>
                <div className="reveal-on-hover" style={{
                  fontSize: 10,
                  color: 'var(--color-text-tertiary)',
                  marginTop: 1,
                }}>
                  {action.message}
                </div>
              </div>

              {/* Outcome badge — verification_status wins over raw status */}
              {(() => {
                const outcome = effectiveOutcome(action);
                return (
                  <span className={`badge ${outcome === 'success' ? 'badge-success' : outcome === 'pending' ? 'badge-warning' : 'badge-error'}`} style={{
                    fontSize: 9,
                    padding: '1px 8px',
                  }}>
                    {outcome === 'success' ? 'Healed' : outcome === 'pending' ? 'Verifying' : 'Failed'}
                  </span>
                );
              })()}
            </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   DATA STREAM CONNECTOR
   ═══════════════════════════════════════════════════════════════════ */

function DataStreamConnector({ hasAnomalies }: { hasAnomalies: boolean }) {
  const { isDark } = useTheme();
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 48,
      flexShrink: 0,
      alignSelf: 'stretch',
    }}>
      <svg width="48" height="100%" viewBox="0 0 48 200" preserveAspectRatio="none" style={{ overflow: 'visible' }}>
        <defs>
          <linearGradient id="streamGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)'} stopOpacity="0.1" />
            <stop offset="50%" stopColor={hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)'} stopOpacity="0.6" />
            <stop offset="100%" stopColor={hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)'} stopOpacity="0.1" />
          </linearGradient>
        </defs>
        <line
          x1="4" y1="100" x2="44" y2="100"
          className={`data-stream-line ${hasAnomalies ? 'warning' : 'active'}`}
        />
        {/* Flowing dot */}
        <circle r="3" fill={hasAnomalies ? 'var(--color-status-warning)' : 'var(--color-accent-primary)'} opacity="0.8">
          <animateMotion
            dur="1.5s"
            repeatCount="indefinite"
            path="M4,100 L44,100"
          />
        </circle>
      </svg>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AI COPILOT PANEL (Floating)
   ═══════════════════════════════════════════════════════════════════ */

function CopilotPanel() {
  const { isDark } = useTheme();
  const [isOpen, setIsOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'ai'; text: string }>>([
    { role: 'ai', text: "I'm monitoring your infrastructure. Ask about system health, patterns, or recommendations." },
  ]);

  const handleSend = () => {
    if (!chatInput.trim()) return;
    const q = chatInput.trim();
    setChatInput('');
    setMessages(p => [...p, { role: 'user', text: q }]);
    setTimeout(() => {
      setMessages(p => [...p, {
        role: 'ai',
        text: `Analyzing: "${q}". Processing across observation logs, anomaly patterns, and healing history. ML models will surface precise insights in the next iteration.`,
      }]);
    }, 1200);
  };

  return (
    <>
      {/* Toggle button */}
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        style={{
          position: 'fixed',
          bottom: 'var(--space-6)',
          right: 'var(--space-6)',
          width: 52,
          height: 52,
          borderRadius: 'var(--radius-full)',
          background: 'var(--color-accent-primary)',
          color: 'var(--color-text-inverse)',
          display: isOpen ? 'none' : 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          cursor: 'pointer',
          zIndex: 300,
          boxShadow: isDark ? '0 0 20px var(--glow-primary)' : 'var(--shadow-lg)',
        }}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </motion.button>

      {/* Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="glass"
            style={{
              position: 'fixed',
              bottom: 'var(--space-6)',
              right: 'var(--space-6)',
              width: 380,
              maxHeight: 500,
              borderRadius: 'var(--radius-xl)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              zIndex: 300,
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: 'var(--space-4) var(--space-5)',
              borderBottom: '1px solid var(--color-border-subtle)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span className="dot dot-success dot-live" />
                <span style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-sm)',
                  fontWeight: 'var(--font-weight-semibold)',
                  color: 'var(--color-text-primary)',
                }}>
                  AI Copilot
                </span>
              </div>
              <button onClick={() => setIsOpen(false)} className="btn-icon" style={{ width: 28, height: 28 }}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M4 4l8 8M12 4l-8 8" />
                </svg>
              </button>
            </div>
{/* 
            Threat chips
            <div style={{
              display: 'flex',
              gap: 'var(--space-1)',
              padding: 'var(--space-2) var(--space-4)',
              flexWrap: 'wrap',
            }}>
              {AI_RECOMMENDATIONS.map(r => (
                <span
                  key={r.id}
                  className={`badge ${r.severity === 'high' ? 'badge-error' : r.severity === 'medium' ? 'badge-warning' : 'badge-neutral'}`}
                  style={{ fontSize: 9, padding: '1px 6px' }}
                >
                  {r.severity.toUpperCase()}: {r.title.split(' ').slice(0, 4).join(' ')}...
                </span>
              ))}
            </div> */}

            {/* Messages */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: 'var(--space-3) var(--space-4)',
              maxHeight: 280,
            }}>
              {messages.map((m, i) => (
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
                    background: m.role === 'user' ? 'var(--color-accent-tertiary)' : 'var(--color-bg-sunken)',
                    border: '1px solid var(--color-border-subtle)',
                    fontSize: 'var(--text-xs)',
                    lineHeight: 'var(--leading-normal)',
                    color: m.role === 'user' ? 'var(--color-accent-primary)' : 'var(--color-text-secondary)',
                  }}>
                    {m.text}
                  </div>
                </div>
              ))}
            </div>

            {/* Input */}
            <div style={{
              padding: 'var(--space-3) var(--space-4)',
              borderTop: '1px solid var(--color-border-subtle)',
              display: 'flex',
              gap: 'var(--space-2)',
            }}>
              <input
                type="text"
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSend()}
                placeholder="Ask about system health..."
                className="input"
                style={{
                  flex: 1,
                  height: 36,
                  padding: '0 var(--space-3)',
                  fontSize: 'var(--text-xs)',
                  borderRadius: 'var(--radius-md)',
                }}
              />
              <button
                onClick={handleSend}
                className="btn-primary ripple-host"
                onMouseDown={(e) => createRipple(e)}
                style={{
                  height: 36,
                  padding: '0 var(--space-4)',
                  fontSize: 'var(--text-xs)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                Send
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   MAIN PAGE COMPONENT
   ═══════════════════════════════════════════════════════════════════ */

export default function LiveVisualizer() {
  const data = useNiramayData();
  const { isDark } = useTheme();
  const hasAnomalies = data.anomalies.length > 0;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--page-gradient)' }}>
      <Navbar />

      <main style={{
        maxWidth: 1440,
        margin: '0 auto',
        padding: '88px var(--space-6) var(--space-12)',
      }}>
        {/* Page Title */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          style={{
            marginBottom: 'var(--space-6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h1 style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-2xl)',
              fontWeight: 'var(--font-weight-bold)',
              color: 'var(--color-text-primary)',
              letterSpacing: 'var(--tracking-tight)',
              marginBottom: 'var(--space-1)',
            }}>
              Live Operations
            </h1>
            <p style={{
              fontSize: 'var(--text-sm)',
              color: 'var(--color-text-tertiary)',
            }}>
              Real-time pipeline: Observation → Detection → Healing
            </p>
          </div>
        </motion.div>

        {/* Metrics Bar */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          style={{ marginBottom: 'var(--space-6)' }}
        >
          <MetricsBar
            metrics={data.metrics}
            isLive={data.isLive}
            setIsLive={data.setIsLive}
            lastRefresh={data.lastRefresh}
            fetchData={data.fetchData}
          />
        </motion.div>

        {/* Pipeline Stage Indicator — reused from Dashboard */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          style={{ marginBottom: 'var(--space-6)' }}
        >
          <PipelineProgressBar />
        </motion.div>

        {/* Pipeline: 3 stages + connectors */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          style={{
            display: 'flex',
            gap: 0,
            alignItems: 'stretch',
          }}
        >
          <ObservationStream logs={data.logs} />
          <DataStreamConnector hasAnomalies={hasAnomalies} />
          <DetectionEngine anomalies={data.anomalies} stats={data.stats} />
          <DataStreamConnector hasAnomalies={hasAnomalies} />
          <HealingOutput actions={data.healingActions} />
        </motion.div>
      </main>

      {/* Floating AI Copilot */}
      <CopilotPanel />

      {/* Responsive */}
      <style>{`
        @media (max-width: 1024px) {
          main > div:last-of-type {
            flex-direction: column !important;
          }
          main > div:last-of-type > div:nth-child(2),
          main > div:last-of-type > div:nth-child(4) {
            width: 100% !important;
            height: 32px !important;
            align-self: center !important;
          }
          main > div:last-of-type > div:nth-child(2) svg,
          main > div:last-of-type > div:nth-child(4) svg {
            transform: rotate(90deg);
          }
        }
      `}</style>
    </div>
  );
}

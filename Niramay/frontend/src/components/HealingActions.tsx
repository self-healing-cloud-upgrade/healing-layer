/**
 * HealingActionsPanel — Healing action feed.
 * Glass panel. Action type pill badges. Icon containers.
 * Progressive disclosure on hover. All data contracts preserved.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { timeAgo, type HealingAction } from '../designSystem';
import EmptyState from './EmptyState';
import { SkeletonRow } from './SkeletonBlock';

/**
 * verification_status is the definitive healing outcome.
 * Returns 'pending' when the action failed but the verification worker hasn't
 * confirmed the result yet — prevents a premature "Failed" badge while the
 * system is still in the settling/verification window.
 */
function effectiveOutcome(a: { status?: string; verification_status?: string }): 'success' | 'failed' | 'pending' {
  if (a.verification_status === 'HEALED' || a.verification_status === 'SUCCESS') return 'success';
  if (a.verification_status === 'FAILED' || a.verification_status === 'ESCALATED') return 'failed';
  if (a.status === 'success') return 'success';
  return 'pending';
}

function ActionIcon({ action }: { action: string }) {
  const s = 15;
  const stroke = 'var(--color-accent-primary)';
  const props = { width: s, height: s, viewBox: "0 0 16 16", fill: "none", stroke, strokeWidth: "1.3", strokeLinecap: "round" as const };

  if (action === 'restart_service') return (
    <svg {...props}>
      <path d="M13 8A5 5 0 1 1 8 3" /><polyline points="13 3 13 8 8 8" />
    </svg>
  );
  if (action === 'scale_up') return (
    <svg {...props}>
      <line x1="8" y1="13" x2="8" y2="3" /><polyline points="4 7 8 3 12 7" />
      <line x1="4" y1="13" x2="12" y2="13" />
    </svg>
  );
  if (action === 'rollback_deployment') return (
    <svg {...props}>
      <path d="M3 8A5 5 0 1 0 8 3" /><polyline points="3 3 3 8 8 8" />
    </svg>
  );
  if (action === 'circuit_breaker') return (
    <svg {...props}>
      <path d="M9 2L7 9h4L9 14" strokeLinejoin="round" />
    </svg>
  );
  if (action === 'flush_cache') return (
    <svg {...props}>
      <polyline points="3 6 5 6 13 6" /><path d="M4 6l1 8a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2l1-8" />
      <path d="M7 6V4a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v2" />
    </svg>
  );
  if (action === 'throttle_requests') return (
    <svg {...props}>
      <rect x="2" y="2" width="12" height="12" rx="2" /><path d="M2 8h12M8 2v12" />
    </svg>
  );
  if (action === 'fallback_response') return (
    <svg {...props}>
      <path d="M1 8h14M1 8l4-4M1 8l4 4" />
    </svg>
  );
  return (
    <svg {...props}>
      <circle cx="8" cy="8" r="6" /><line x1="8" y1="5" x2="8" y2="8" /><line x1="8" y1="8" x2="10" y2="10" />
    </svg>
  );
}

export default function HealingActionsPanel({ actions }: { actions: HealingAction[] }) {
  // Filter out batched/suppressed/skipped — only show real healing outcomes
  const visibleActions = (actions || []).filter(a => a && (a.status === 'success' || a.status === 'failed'));
  const byType = visibleActions.reduce<Record<string, number>>((acc, x) => {
    if (x && x.healing_action) {
      acc[x.healing_action] = (acc[x.healing_action] || 0) + 1;
    }
    return acc;
  }, {});

  return (
    <div
      id="healing-actions"
      className="glass card-glass"
      style={{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
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
          Healing
        </span>
        {visibleActions.filter(a => effectiveOutcome(a) === 'success').length > 0 && (
          <span className="badge badge-success">
            {visibleActions.filter(a => effectiveOutcome(a) === 'success').length} healed
          </span>
        )}
        {visibleActions.filter(a => effectiveOutcome(a) === 'pending').length > 0 && (
          <span className="badge badge-warning" style={{ marginLeft: 4 }}>
            {visibleActions.filter(a => effectiveOutcome(a) === 'pending').length} verifying
          </span>
        )}
        {visibleActions.filter(a => effectiveOutcome(a) === 'failed').length > 0 && (
          <span className="badge badge-error" style={{ marginLeft: 4 }}>
            {visibleActions.filter(a => effectiveOutcome(a) === 'failed').length} failed
          </span>
        )}
      </div>

      {/* Action type chips */}
      {Object.keys(byType).length > 0 && (
        <div style={{
          display: 'flex',
          gap: 'var(--space-2)',
          padding: '0 var(--space-6) var(--space-3)',
          flexWrap: 'wrap',
        }}>
          {Object.entries(byType).map(([t, c]) => (
            <span key={t} className="badge badge-neutral" style={{
              gap: 'var(--space-1)',
            }}>
              {t.replace(/_/g, ' ')}
              <strong style={{ fontWeight: 'var(--font-weight-semibold)' as any }}>
                {c}
              </strong>
            </span>
          ))}
        </div>
      )}

      {/* Action rows */}
      <div className="scroll-fade" style={{
        flex: 1,
        padding: 'var(--space-2) var(--space-6) var(--space-6)',
        maxHeight: 360,
        overflowY: 'auto',
      }}>
        {visibleActions.length === 0 ? (
          <EmptyState headline="No healing actions yet" />
        ) : (
          <AnimatePresence initial={false}>
            {visibleActions.map((a, i) => 
              a ? (
                <motion.div
                  key={`${a.timestamp}-${i}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.3,
                  delay: Math.min(i * 0.04, 0.4),
                  ease: [0.16, 1, 0.3, 1],
                }}
                className="row-interactive"
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 'var(--space-3)',
                  padding: 'var(--space-3) var(--space-2)',
                  cursor: 'default',
                  borderRadius: 'var(--radius-md)',
                  background: effectiveOutcome(a) === 'failed'
                    ? 'rgba(239,68,68,0.04)'
                    : effectiveOutcome(a) === 'success'
                    ? 'rgba(16,185,129,0.04)'
                    : effectiveOutcome(a) === 'pending'
                    ? 'rgba(245,158,11,0.04)'
                    : undefined,
                }}
              >
                {/* Icon container */}
                <div style={{
                  width: 32,
                  height: 32,
                  borderRadius: 'var(--radius-md)',
                  background: effectiveOutcome(a) === 'failed'
                    ? 'rgba(239,68,68,0.08)'
                    : effectiveOutcome(a) === 'pending'
                    ? 'rgba(245,158,11,0.08)'
                    : 'var(--color-accent-tertiary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  marginTop: 2,
                }}>
                  <ActionIcon action={a.healing_action} />
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 2,
                  }}>
                    <span style={{
                      fontSize: 'var(--text-sm)',
                      fontWeight: 'var(--font-weight-regular)' as any,
                      color: 'var(--color-text-primary)',
                      textTransform: 'capitalize',
                    }}>
                      {a.healing_action.replace(/_/g, ' ')}
                    </span>

                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                      {a.retry_count != null && a.retry_count > 0 && (
                        <span className="badge badge-neutral" style={{ fontSize: 9, padding: '1px 4px' }}>
                          Attempt {a.retry_count + 1}
                        </span>
                      )}
                      {(a.verification_status === 'SUCCESS' || a.verification_status === 'HEALED'
                        || a.verification_status === 'FAILED' || a.verification_status === 'ESCALATED') && (
                        <span className={`badge badge-${
                          a.verification_status === 'SUCCESS' || a.verification_status === 'HEALED'
                            ? 'success' : 'error'
                        }`} style={{ fontSize: 9, padding: '1px 4px' }}>
                          {a.verification_status === 'SUCCESS' || a.verification_status === 'HEALED'
                            ? 'PASSED' : 'FAILED'}
                        </span>
                      )}
                      <span className={`dot dot-${effectiveOutcome(a) === 'success' ? 'success' : effectiveOutcome(a) === 'failed' ? 'error' : 'warning'}`} />
                    </div>
                  </div>

                  {/* Service + container context */}
                  {(a.service || a.container_restarted) && (
                    <div style={{
                      display: 'flex',
                      gap: 'var(--space-3)',
                      marginTop: 'var(--space-1)',
                      fontSize: 10,
                      color: 'var(--color-text-tertiary)',
                      fontFamily: 'var(--font-mono)',
                    }}>
                      {a.service && <span>Service: {a.service}</span>}
                      {a.container_restarted && <span>Container: {a.container_restarted}</span>}
                    </div>
                  )}

                  {/* K3s result detail — shown when K3s healing fields are present */}
                  {(a.new_replicas != null || a.rolled_back_to || a.original_replicas != null || a.throttled_replicas != null) && (
                    <div style={{
                      display: 'flex',
                      gap: 'var(--space-3)',
                      marginTop: 'var(--space-1)',
                      fontSize: 10,
                      color: 'var(--color-text-tertiary)',
                      fontFamily: 'var(--font-mono)',
                      flexWrap: 'wrap',
                    }}>
                      {a.new_replicas != null && a.previous_replicas != null && (
                        <span>Replicas: {a.previous_replicas} → {a.new_replicas}</span>
                      )}
                      {a.throttled_replicas != null && a.previous_replicas != null && (
                        <span>Throttled: {a.previous_replicas} → {a.throttled_replicas}</span>
                      )}
                      {a.original_replicas != null && a.circuit_duration != null && (
                        <span>Circuit open {a.circuit_duration}s (restores to {a.original_replicas})</span>
                      )}
                      {a.rolled_back_to && (
                        <span>Rolled back to: {a.rolled_back_to}</span>
                      )}
                      {a.k3s_deployment && (
                        <span>Deployment: {a.k3s_deployment}</span>
                      )}
                    </div>
                  )}

                  {/* Scenarios disabled */}
                  {a.scenarios_disabled && a.scenarios_disabled.length > 0 && (
                    <div style={{
                      marginTop: 'var(--space-1)',
                      fontSize: 10,
                      color: 'var(--color-status-success)',
                      fontFamily: 'var(--font-mono)',
                    }}>
                      Disabled: {a.scenarios_disabled.join(', ')}
                    </div>
                  )}

                  {/* Error — only on failed */}
                  {a.status === 'failed' && a.error && (
                    <div style={{
                      marginTop: 'var(--space-1)',
                      fontSize: 10,
                      color: 'var(--color-status-error)',
                      fontFamily: 'var(--font-mono)',
                    }}>
                      {a.error}
                    </div>
                  )}

                  {/* Message — revealed on hover */}
                  <div className="reveal-on-hover" style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--color-text-tertiary)',
                    lineHeight: 'var(--leading-normal)',
                    marginTop: 2,
                  }}>
                    {a.message}
                  </div>

                  {/* Time */}
                  <span className="subtle-on-hover" style={{
                    fontSize: 10,
                    color: 'var(--color-text-tertiary)',
                    marginTop: 'var(--space-1)',
                    display: 'block',
                  }}>
                    {timeAgo(a.timestamp)}
                  </span>
                </div>
              </motion.div>
            ) : null
          )}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}

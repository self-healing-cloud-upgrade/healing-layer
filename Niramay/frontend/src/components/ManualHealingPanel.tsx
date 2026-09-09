/**
 * ManualHealingPanel — Feature 6 (Manual mode).
 *
 * Right-side slide-in panel (480px) listing pending healing actions.
 * Shown when healing mode is 'manual'. Each action has Approve / Reject buttons.
 * Calls POST /api/v1/healing/pending/{id}/decision.
 */

import { AnimatePresence, motion } from 'framer-motion';
import { useHealingMode } from '../hooks/useHealingMode';
import { timeAgo } from '../designSystem';

export default function ManualHealingPanel() {
  const { healingMode, pendingActions, decideAction } = useHealingMode();

  const isOpen = healingMode.mode === 'manual';

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop (semi-transparent, non-blocking) */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.3)',
              zIndex: 700,
              pointerEvents: 'none',
            }}
            aria-hidden="true"
          />

          {/* Drawer */}
          <motion.aside
            initial={{ x: 500 }}
            animate={{ x: 0 }}
            exit={{ x: 500 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0,
              width: 480, zIndex: 800,
              background: 'var(--color-bg-primary)',
              borderLeft: '1px solid var(--color-border-default)',
              display: 'flex', flexDirection: 'column',
              boxShadow: '-4px 0 32px rgba(0,0,0,0.25)',
            }}
            role="complementary"
            aria-label="Manual healing actions"
          >
            {/* Header */}
            <div style={{
              padding: 'var(--space-5) var(--space-6)',
              borderBottom: '1px solid var(--color-border-subtle)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              flexShrink: 0,
            }}>
              <div>
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-md)', color: 'var(--color-text-primary)' }}>
                  Healing Actions
                </span>
                {pendingActions.length > 0 && (
                  <span className="badge badge-warning" style={{ marginLeft: 8 }}>
                    {pendingActions.length} pending
                  </span>
                )}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)',
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <span className="dot dot-warning" style={{ animation: 'pulse 2s infinite' }} />
                Manual mode active
              </div>
            </div>

            {/* Action list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-4) var(--space-6)' }}>
              {pendingActions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 'var(--space-16) 0', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>
                  <p>No pending actions.</p>
                  <p style={{ fontSize: 'var(--text-xs)', marginTop: 4 }}>Actions will appear here when healing detects an issue.</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                  {pendingActions.map(action => (
                    <div
                      key={action.action_id}
                      className="glass"
                      style={{
                        borderRadius: 'var(--radius-lg)',
                        padding: 'var(--space-4)',
                        border: '1px solid var(--color-border-subtle)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-2)' }}>
                        <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', textTransform: 'capitalize' }}>
                          {action.healing_action.replace(/_/g, ' ')}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                          {timeAgo(action.timestamp)}
                        </span>
                      </div>

                      {(action.service || action.endpoint) && (
                        <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)', marginBottom: 'var(--space-2)' }}>
                          {action.service && <span>Service: {action.service}</span>}
                          {action.endpoint && <span style={{ marginLeft: 8 }}>Endpoint: {action.endpoint}</span>}
                        </div>
                      )}

                      <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-3)', lineHeight: 'var(--leading-normal)' }}>
                        {action.message}
                      </p>

                      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                        <button
                          id={`approve-${action.action_id}`}
                          onClick={() => decideAction(action.action_id, 'approve')}
                          className="ripple-host"
                          aria-label={`Approve action: ${action.healing_action}`}
                          style={{
                            flex: 1, padding: '7px 12px',
                            borderRadius: 'var(--radius-md)',
                            background: 'rgba(45,122,79,0.1)',
                            border: '1px solid rgba(45,122,79,0.25)',
                            color: 'var(--color-status-success)',
                            fontSize: 'var(--text-xs)', fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          ✓ Approve
                        </button>
                        <button
                          id={`reject-${action.action_id}`}
                          onClick={() => decideAction(action.action_id, 'reject')}
                          className="ripple-host"
                          aria-label={`Reject action: ${action.healing_action}`}
                          style={{
                            flex: 1, padding: '7px 12px',
                            borderRadius: 'var(--radius-md)',
                            background: 'rgba(239,68,68,0.07)',
                            border: '1px solid rgba(239,68,68,0.2)',
                            color: 'var(--color-status-error)',
                            fontSize: 'var(--text-xs)', fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          ✕ Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

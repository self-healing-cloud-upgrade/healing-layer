/**
 * HealingModeModal — Root-level mandatory modal (Feature 6).
 *
 * Appears when pipeline stage reaches 'stage_4_healing_executing'
 * AND no mode has been chosen yet this session.
 *
 * - No dismiss/close button — user MUST choose a mode.
 * - Focus is trapped within the modal (WCAG 2.1 AA).
 * - Focus is restored to the trigger element on close.
 * - Calls POST /api/v1/healing/mode on selection.
 * - Fires a toast notification after selection.
 * - If mode is 'manual', the ManualHealingPanel is shown via a shared flag.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useHealingMode } from '../hooks/useHealingMode';
import { usePipelineStage } from '../hooks/useNiramayData';
import { useToast } from './ToastNotification';

function AutoIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
      stroke="var(--color-accent-primary)" strokeWidth="1.5" strokeLinecap="round">
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  );
}

function ManualIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
      stroke="var(--color-accent-primary)" strokeWidth="1.5" strokeLinecap="round">
      <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v5" />
      <path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v6" />
      <path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8" />
      <path d="M6 14v0a4 4 0 0 0 4 4h4a4 4 0 0 0 4-4v-1" />
    </svg>
  );
}

export default function HealingModeModal() {
  const pipelineStage = usePipelineStage(true);
  const { healingMode, setMode, loading } = useHealingMode();
  const { addToast } = useToast();

  /** Whether the modal was dismissed this session (mode was set). */
  const [dismissed, setDismissed] = useState(false);
  const [whyExpanded, setWhyExpanded] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const prevFocusRef = useRef<Element | null>(null);

  const isOpen =
    !dismissed &&
    pipelineStage?.stage === 'stage_4_healing_executing' &&
    healingMode.mode === null;

  // Save focus when opening, restore when closing
  useEffect(() => {
    if (isOpen) {
      prevFocusRef.current = document.activeElement;
      setTimeout(() => modalRef.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus(), 50);
    } else if (prevFocusRef.current instanceof HTMLElement) {
      prevFocusRef.current.focus();
    }
  }, [isOpen]);

  // Trap focus inside modal
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab') return;
    const focusable = modalRef.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
      e.preventDefault();
      (e.shiftKey ? last : first).focus();
    }
  }, []);

  const handleSelect = useCallback(async (mode: 'autonomous' | 'manual') => {
    await setMode(mode);
    setDismissed(true);
    addToast(
      mode === 'autonomous'
        ? 'Autonomous healing started'
        : 'Manual healing started — awaiting your input',
      'success'
    );
  }, [setMode, addToast]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          style={{
            position: 'fixed', inset: 0, zIndex: 8000,
            background: 'rgba(0,0,0,0.7)',
            backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 'var(--space-4)',
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="healing-modal-title"
        >
          <motion.div
            ref={modalRef}
            onKeyDown={handleKeyDown}
            initial={{ scale: 0.95, opacity: 0, y: 16 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 8 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="glass"
            style={{
              width: '100%', maxWidth: 560,
              borderRadius: 'var(--radius-xl)',
              padding: 'var(--space-8)',
              border: '1px solid var(--color-border-default)',
            }}
          >
            {/* Header */}
            <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
              <div style={{
                width: 48, height: 48, borderRadius: 'var(--radius-full)',
                background: 'rgba(212,132,94,0.1)',
                border: '1px solid rgba(212,132,94,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto var(--space-4)',
              }}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                  stroke="var(--color-accent-primary)" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" />
                  <path d="M2 17l10 5 10-5" />
                  <path d="M2 12l10 5 10-5" />
                </svg>
              </div>
              <h2 id="healing-modal-title" style={{
                fontFamily: 'var(--font-display)',
                fontSize: 'var(--text-xl)',
                color: 'var(--color-text-primary)',
                marginBottom: 'var(--space-2)',
                fontWeight: 600,
              }}>
                Healing has started
              </h2>
              <p style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text-tertiary)',
                lineHeight: 'var(--leading-loose)',
              }}>
                Choose how you'd like to proceed with the healing process.
              </p>
            </div>

            {/* Mode Cards */}
            <div style={{ display: 'flex', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
              {/* Autonomous */}
              <button
                data-autofocus
                id="healing-mode-autonomous"
                disabled={loading}
                onClick={() => handleSelect('autonomous')}
                style={{
                  flex: 1, textAlign: 'left',
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-default)',
                  borderRadius: 'var(--radius-lg)',
                  padding: 'var(--space-5)',
                  cursor: loading ? 'wait' : 'pointer',
                  transition: 'border-color 200ms, box-shadow 200ms',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-accent-primary)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border-default)'; }}
                onFocus={e => { (e.currentTarget as HTMLElement).style.boxShadow = '0 0 0 2px var(--color-accent-primary)'; }}
                onBlur={e => { (e.currentTarget as HTMLElement).style.boxShadow = 'none'; }}
                aria-label="Start Autonomous Healing"
              >
                <div style={{ marginBottom: 'var(--space-3)' }}><AutoIcon /></div>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', marginBottom: 'var(--space-2)' }}>
                  Autonomous
                </div>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', lineHeight: 'var(--leading-loose)', margin: 0 }}>
                  Consumer and healing run simultaneously. No user input required. The system will resolve anomalies automatically.
                </p>
                <div style={{
                  marginTop: 'var(--space-4)',
                  padding: '8px 16px',
                  borderRadius: 'var(--radius-md)',
                  background: 'rgba(212,132,94,0.1)',
                  color: 'var(--color-accent-primary)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  textAlign: 'center',
                }}>
                  Start Autonomous Healing
                </div>
              </button>

              {/* Manual */}
              <button
                id="healing-mode-manual"
                disabled={loading}
                onClick={() => handleSelect('manual')}
                style={{
                  flex: 1, textAlign: 'left',
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-default)',
                  borderRadius: 'var(--radius-lg)',
                  padding: 'var(--space-5)',
                  cursor: loading ? 'wait' : 'pointer',
                  transition: 'border-color 200ms, box-shadow 200ms',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-accent-primary)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border-default)'; }}
                onFocus={e => { (e.currentTarget as HTMLElement).style.boxShadow = '0 0 0 2px var(--color-accent-primary)'; }}
                onBlur={e => { (e.currentTarget as HTMLElement).style.boxShadow = 'none'; }}
                aria-label="Start Manual Healing"
              >
                <div style={{ marginBottom: 'var(--space-3)' }}><ManualIcon /></div>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', marginBottom: 'var(--space-2)' }}>
                  Manual
                </div>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', lineHeight: 'var(--leading-loose)', margin: 0 }}>
                  Healing pauses at each step for your confirmation. You control which actions are applied.
                </p>
                <div style={{
                  marginTop: 'var(--space-4)',
                  padding: '8px 16px',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-default)',
                  color: 'var(--color-text-secondary)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  textAlign: 'center',
                }}>
                  Start Manual Healing
                </div>
              </button>
            </div>

            {/* Why do I need to choose? */}
            <div style={{ textAlign: 'center' }}>
              <button
                id="healing-why-toggle"
                onClick={() => setWhyExpanded(v => !v)}
                style={{
                  background: 'none', border: 'none',
                  color: 'var(--color-text-tertiary)',
                  fontSize: 'var(--text-xs)',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  padding: 0,
                }}
                aria-expanded={whyExpanded}
                aria-controls="healing-why-content"
              >
                Why do I need to choose?
              </button>
              <AnimatePresence>
                {whyExpanded && (
                  <motion.div
                    id="healing-why-content"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    style={{ overflow: 'hidden' }}
                  >
                    <p style={{
                      marginTop: 'var(--space-3)',
                      fontSize: 'var(--text-xs)',
                      color: 'var(--color-text-tertiary)',
                      lineHeight: 'var(--leading-loose)',
                      background: 'var(--color-bg-secondary)',
                      borderRadius: 'var(--radius-md)',
                      padding: 'var(--space-3) var(--space-4)',
                      border: '1px solid var(--color-border-subtle)',
                      textAlign: 'left',
                    }}>
                      <strong style={{ color: 'var(--color-text-primary)' }}>Autonomous mode</strong> runs the full healing pipeline automatically — ideal for production environments where speed matters.{' '}
                      <strong style={{ color: 'var(--color-text-primary)' }}>Manual mode</strong> lets you review and approve each action before it runs — useful in sensitive environments or during incident investigations.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * ToastNotification — Lightweight toast system using framer-motion.
 * No new dependencies. Context-based so any component can fire a toast.
 *
 * Usage:
 *   const { addToast } = useToast();
 *   addToast('Autonomous healing started', 'success');
 */

import {
  createContext, useContext, useState, useCallback,
  type ReactNode, createElement
} from 'react';
import { AnimatePresence, motion } from 'framer-motion';

export type ToastKind = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: string;
  message: string;
  kind: ToastKind;
}

interface ToastCtx {
  addToast: (message: string, kind?: ToastKind) => void;
}

const ToastContext = createContext<ToastCtx>({ addToast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

const KIND_STYLES: Record<ToastKind, { border: string; dot: string }> = {
  success: { border: 'var(--color-status-success)', dot: 'var(--color-status-success)' },
  error:   { border: 'var(--color-status-error)',   dot: 'var(--color-status-error)'   },
  warning: { border: 'var(--color-status-warning)', dot: 'var(--color-status-warning)' },
  info:    { border: 'var(--color-accent-primary)', dot: 'var(--color-accent-primary)' },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts(prev => [...prev, { id, message, kind }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 7500);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return createElement(
    ToastContext.Provider,
    { value: { addToast } },
    children,
    createElement(
      'div',
      {
        role: 'status',
        'aria-live': 'polite',
        'aria-label': 'Notifications',
        style: {
          position: 'fixed',
          top: 80,
          right: 20,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 10,
          pointerEvents: 'none',
        },
      },
      createElement(
        AnimatePresence,
        { initial: false },
        ...toasts.map(t =>
          createElement(
            motion.div,
            {
              key: t.id,
              initial: { opacity: 0, x: 40, scale: 0.95 },
              animate: { opacity: 1, x: 0, scale: 1 },
              exit:    { opacity: 0, x: 20, scale: 0.95 },
              transition: { duration: 0.22, ease: [0.16, 1, 0.3, 1] },
              style: {
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                background: 'var(--color-bg-secondary)',
                border: `1px solid ${KIND_STYLES[t.kind].border}44`,
                borderLeft: `4px solid ${KIND_STYLES[t.kind].border}`,
                borderRadius: 'var(--radius-lg)',
                padding: '14px 24px',
                backdropFilter: 'blur(12px)',
                boxShadow: '0 10px 30px rgba(0,0,0,0.3)',
                maxWidth: 480,
                minWidth: 280,
                pointerEvents: 'auto',
                cursor: 'pointer',
              },
              onClick: () => removeToast(t.id),
            },
            createElement('span', {
              style: {
                width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                background: KIND_STYLES[t.kind].dot,
              },
            }),
            createElement('span', {
              style: {
                fontSize: 'var(--text-md)',
                fontWeight: 500,
                color: 'var(--color-text-primary)',
                lineHeight: 'var(--leading-normal)',
              },
            }, t.message),
          )
        )
      )
    )
  );
}

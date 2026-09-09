/**
 * ModeSelectionScreen — Startup mode selector (Feature: Mode Selection on Startup)
 *
 * Appears once on first load before the main interface.
 * User chooses between Manual Mode (toggles OFF) and AI Mode (toggles ON).
 * Calls backend APIs to set consumer and healing toggle states accordingly.
 */

import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useTheme } from '../designSystem';

interface ModeSelectionScreenProps {
  onSelect: (mode: 'manual' | 'ai') => void;
}

export default function ModeSelectionScreen({ onSelect }: ModeSelectionScreenProps) {
  const { isDark } = useTheme();
  const [loading, setLoading] = useState(false);
  const [hoveredCard, setHoveredCard] = useState<'manual' | 'ai' | null>(null);

  const handleSelect = useCallback(async (mode: 'manual' | 'ai') => {
    setLoading(true);
    try {
      if (mode === 'ai') {
        // AI Mode: start consumer + enable healing
        await fetch('/api/v1/consumer/start', { method: 'POST' });
        await fetch('/api/v1/healing/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: true }),
        });
      }
      // Manual Mode: both stay OFF (backend defaults to OFF on startup)
    } catch (err) {
      console.error('Mode selection API error:', err);
    }
    setLoading(false);
    onSelect(mode);
  }, [onSelect]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: isDark
          ? 'radial-gradient(ellipse at center, rgba(20,16,12,0.97), rgba(10,8,6,1))'
          : 'radial-gradient(ellipse at center, rgba(250,248,245,0.98), rgba(240,237,230,1))',
        padding: 'var(--space-4)',
      }}
    >
      {/* Decorative background orbs */}
      <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
        <div style={{
          position: 'absolute', width: 400, height: 400,
          borderRadius: '50%',
          background: isDark
            ? 'radial-gradient(circle, rgba(212,132,94,0.06) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(196,101,58,0.04) 0%, transparent 70%)',
          top: '10%', left: '15%',
          animation: 'float 8s ease-in-out infinite',
        }} />
        <div style={{
          position: 'absolute', width: 300, height: 300,
          borderRadius: '50%',
          background: isDark
            ? 'radial-gradient(circle, rgba(212,132,94,0.04) 0%, transparent 70%)'
            : 'radial-gradient(circle, rgba(196,101,58,0.03) 0%, transparent 70%)',
          bottom: '15%', right: '10%',
          animation: 'floatReverse 6s ease-in-out infinite',
        }} />
      </div>

      <motion.div
        initial={{ scale: 0.92, opacity: 0, y: 24 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: 640,
          textAlign: 'center',
        }}
      >
        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          style={{ marginBottom: 'var(--space-3)' }}
        >
          <div style={{
            width: 56, height: 56,
            borderRadius: 'var(--radius-lg)',
            background: 'linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-secondary))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto var(--space-4)',
            boxShadow: isDark
              ? '0 0 30px rgba(212,132,94,0.25), 0 4px 20px rgba(0,0,0,0.4)'
              : '0 4px 20px rgba(196,101,58,0.15), 0 2px 10px rgba(0,0,0,0.08)',
          }}>
            <svg width="24" height="24" viewBox="0 0 16 16" fill="none">
              <path d="M8 2L14 6V14H2V6L8 2Z" stroke={isDark ? '#0A0E17' : '#fff'} strokeWidth="1.5" fill="none" />
              <circle cx="8" cy="9" r="2" fill={isDark ? '#0A0E17' : '#fff'} />
            </svg>
          </div>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-3xl)',
            fontWeight: 600,
            color: 'var(--color-text-primary)',
            letterSpacing: 'var(--tracking-tight)',
            marginBottom: 'var(--space-2)',
            lineHeight: 'var(--leading-tight)',
          }}
        >
          Welcome to Niramay
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 0.5 }}
          style={{
            fontSize: 'var(--text-base)',
            color: 'var(--color-text-tertiary)',
            lineHeight: 'var(--leading-loose)',
            maxWidth: 420,
            margin: '0 auto var(--space-8)',
          }}
        >
          Choose how you'd like to operate the self-healing pipeline
        </motion.p>

        {/* Mode cards */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.5 }}
          style={{
            display: 'flex',
            gap: 'var(--space-5)',
            justifyContent: 'center',
            marginBottom: 'var(--space-6)',
          }}
        >
          {/* Manual Mode */}
          <motion.button
            id="mode-select-manual"
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            disabled={loading}
            onClick={() => handleSelect('manual')}
            onMouseEnter={() => setHoveredCard('manual')}
            onMouseLeave={() => setHoveredCard(null)}
            style={{
              flex: 1, maxWidth: 280,
              textAlign: 'left',
              background: hoveredCard === 'manual'
                ? (isDark ? 'rgba(30,27,23,0.9)' : 'rgba(255,255,255,0.95)')
                : 'var(--color-bg-secondary)',
              border: hoveredCard === 'manual'
                ? '1px solid var(--color-accent-primary)'
                : '1px solid var(--color-border-default)',
              borderRadius: 'var(--radius-xl)',
              padding: 'var(--space-6)',
              cursor: loading ? 'wait' : 'pointer',
              transition: 'all 200ms ease',
              boxShadow: hoveredCard === 'manual'
                ? (isDark ? '0 0 20px rgba(212,132,94,0.1)' : '0 4px 24px rgba(0,0,0,0.08)')
                : 'none',
            }}
          >
            {/* Icon */}
            <div style={{
              width: 44, height: 44,
              borderRadius: 'var(--radius-lg)',
              background: 'rgba(212,132,94,0.08)',
              border: '1px solid rgba(212,132,94,0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 'var(--space-4)',
            }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke="var(--color-accent-primary)" strokeWidth="1.5" strokeLinecap="round">
                <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v5" />
                <path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v6" />
                <path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8" />
                <path d="M6 14v0a4 4 0 0 0 4 4h4a4 4 0 0 0 4-4v-1" />
              </svg>
            </div>

            <div style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              fontSize: 'var(--text-lg)',
              color: 'var(--color-text-primary)',
              marginBottom: 'var(--space-2)',
            }}>
              Manual Mode
            </div>
            <p style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-tertiary)',
              lineHeight: 'var(--leading-loose)',
              margin: '0 0 var(--space-4) 0',
            }}>
              Consumer and healing toggles start <strong style={{ color: 'var(--color-text-secondary)' }}>OFF</strong>.
              You control when each pipeline component activates.
            </p>

            {/* Toggle preview */}
            <div style={{
              display: 'flex', gap: 'var(--space-3)',
              marginBottom: 'var(--space-4)',
            }}>
              <span style={{
                fontSize: 9, padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(239,68,68,0.06)',
                border: '1px solid rgba(239,68,68,0.15)',
                color: 'var(--color-status-error)',
                letterSpacing: '0.05em', textTransform: 'uppercase', fontWeight: 500,
              }}>Consumer OFF</span>
              <span style={{
                fontSize: 9, padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(239,68,68,0.06)',
                border: '1px solid rgba(239,68,68,0.15)',
                color: 'var(--color-status-error)',
                letterSpacing: '0.05em', textTransform: 'uppercase', fontWeight: 500,
              }}>Healing OFF</span>
            </div>

            <div style={{
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border-default)',
              color: 'var(--color-text-secondary)',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              textAlign: 'center',
            }}>
              Select Manual
            </div>
          </motion.button>

          {/* AI Mode */}
          <motion.button
            id="mode-select-ai"
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            disabled={loading}
            onClick={() => handleSelect('ai')}
            onMouseEnter={() => setHoveredCard('ai')}
            onMouseLeave={() => setHoveredCard(null)}
            style={{
              flex: 1, maxWidth: 280,
              textAlign: 'left',
              background: hoveredCard === 'ai'
                ? (isDark ? 'rgba(30,27,23,0.9)' : 'rgba(255,255,255,0.95)')
                : 'var(--color-bg-secondary)',
              border: hoveredCard === 'ai'
                ? '1px solid var(--color-accent-primary)'
                : '1px solid var(--color-border-default)',
              borderRadius: 'var(--radius-xl)',
              padding: 'var(--space-6)',
              cursor: loading ? 'wait' : 'pointer',
              transition: 'all 200ms ease',
              boxShadow: hoveredCard === 'ai'
                ? (isDark ? '0 0 20px rgba(212,132,94,0.1)' : '0 4px 24px rgba(0,0,0,0.08)')
                : 'none',
            }}
          >
            {/* Icon */}
            <div style={{
              width: 44, height: 44,
              borderRadius: 'var(--radius-lg)',
              background: 'rgba(212,132,94,0.08)',
              border: '1px solid rgba(212,132,94,0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 'var(--space-4)',
            }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                stroke="var(--color-accent-primary)" strokeWidth="1.5" strokeLinecap="round">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4" />
                <circle cx="12" cy="12" r="4" />
              </svg>
            </div>

            <div style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 600,
              fontSize: 'var(--text-lg)',
              color: 'var(--color-text-primary)',
              marginBottom: 'var(--space-2)',
            }}>
              AI Mode
            </div>
            <p style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-tertiary)',
              lineHeight: 'var(--leading-loose)',
              margin: '0 0 var(--space-4) 0',
            }}>
              Consumer and healing toggles start <strong style={{ color: 'var(--color-status-success)' }}>ON</strong>.
              The system autonomously ingests, detects, and heals.
            </p>

            {/* Toggle preview */}
            <div style={{
              display: 'flex', gap: 'var(--space-3)',
              marginBottom: 'var(--space-4)',
            }}>
              <span style={{
                fontSize: 9, padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(45,122,79,0.08)',
                border: '1px solid rgba(45,122,79,0.2)',
                color: 'var(--color-status-success)',
                letterSpacing: '0.05em', textTransform: 'uppercase', fontWeight: 500,
              }}>Consumer ON</span>
              <span style={{
                fontSize: 9, padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(45,122,79,0.08)',
                border: '1px solid rgba(45,122,79,0.2)',
                color: 'var(--color-status-success)',
                letterSpacing: '0.05em', textTransform: 'uppercase', fontWeight: 500,
              }}>Healing ON</span>
            </div>

            <div style={{
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              background: 'rgba(212,132,94,0.1)',
              color: 'var(--color-accent-primary)',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              textAlign: 'center',
            }}>
              {loading ? 'Starting…' : 'Select AI Mode'}
            </div>
          </motion.button>
        </motion.div>

        {/* Footer hint */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8, duration: 0.5 }}
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--color-text-tertiary)',
            opacity: 0.6,
          }}
        >
          You can change toggles anytime from the dashboard navbar
        </motion.p>
      </motion.div>
    </motion.div>
  );
}

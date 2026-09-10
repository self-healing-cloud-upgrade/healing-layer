/**
 * EscalationEmailSettings
 *
 * Compact inline component that lets the user configure
 * the developer email address for escalation alerts.
 * Shows a small input + save button in a glass panel.
 *
 * When healing fails after 3 attempts, the system sends
 * an escalation email to this address.
 */

import { useState, useEffect, useCallback } from 'react';

const API = '';

export default function EscalationEmailSettings() {
  const [email, setEmail] = useState('');
  const [savedEmail, setSavedEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  // Load current email from backend
  const loadEmail = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/escalation/email`);
      if (res.ok) {
        const data = await res.json();
        if (data.email) {
          setEmail(data.email);
          setSavedEmail(data.email);
        }
      }
    } catch {}
  }, []);

  useEffect(() => { loadEmail(); }, [loadEmail]);

  const saveEmail = async () => {
    if (!email.trim()) {
      setStatus('error');
      setErrorMsg('Please enter an email address');
      return;
    }
    if (!email.includes('@') || !email.includes('.')) {
      setStatus('error');
      setErrorMsg('Invalid email address');
      return;
    }

    setStatus('saving');
    setErrorMsg('');
    try {
      const res = await fetch(`${API}/api/v1/escalation/email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (data.success) {
        setSavedEmail(data.email);
        setStatus('saved');
        setTimeout(() => setStatus('idle'), 3000);
      } else {
        setStatus('error');
        setErrorMsg(data.error || 'Failed to save');
      }
    } catch (e: any) {
      setStatus('error');
      setErrorMsg(e.message || 'Network error');
    }
  };

  const hasChanged = email.trim() !== savedEmail;

  return (
    <div
      id="escalation-email-settings"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-5) var(--space-6)',
        marginBottom: 'var(--space-8)',
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-3)',
      }}>
        <span style={{ fontSize: 14 }}>✉️</span>
        <span style={{
          fontSize: 'var(--text-sm)',
          fontWeight: 600,
          color: 'var(--color-text-primary)',
          letterSpacing: 'var(--tracking-tight)',
        }}>
          Escalation Email
        </span>
        <span style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-tertiary)',
          fontStyle: 'italic',
        }}>
          — notified when healing fails after 3 attempts
        </span>
      </div>

      {/* Input row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
      }}>
        <input
          id="escalation-email-input"
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (status === 'error') setStatus('idle');
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') saveEmail();
          }}
          placeholder="developer@example.com"
          style={{
            flex: 1,
            padding: '6px 12px',
            borderRadius: 'var(--radius-md)',
            border: `1px solid ${status === 'error' ? 'var(--color-status-error)' : 'var(--color-border-default)'}`,
            background: 'var(--color-bg-primary)',
            color: 'var(--color-text-primary)',
            fontSize: 'var(--text-sm)',
            fontFamily: 'var(--font-mono)',
            outline: 'none',
            transition: 'border-color 200ms',
          }}
        />

        <button
          id="escalation-email-save"
          onClick={saveEmail}
          disabled={status === 'saving' || !hasChanged}
          style={{
            padding: '6px 16px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid transparent',
            background: hasChanged
              ? 'var(--color-accent-primary)'
              : savedEmail
                ? 'rgba(45,122,79,0.1)'
                : 'var(--color-bg-tertiary)',
            color: hasChanged
              ? '#fff'
              : savedEmail
                ? 'var(--color-status-success)'
                : 'var(--color-text-tertiary)',
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            cursor: hasChanged ? 'pointer' : 'default',
            transition: 'all 200ms',
            letterSpacing: 'var(--tracking-wider)',
            textTransform: 'uppercase',
            opacity: status === 'saving' ? 0.6 : 1,
          }}
        >
          {status === 'saving' ? 'Saving...'
            : status === 'saved' ? '✓ Saved'
            : savedEmail && !hasChanged ? '✓ Configured'
            : 'Save'}
        </button>
      </div>

      {/* Status messages */}
      {status === 'error' && errorMsg && (
        <p style={{
          margin: '6px 0 0',
          fontSize: 'var(--text-xs)',
          color: 'var(--color-status-error)',
        }}>
          {errorMsg}
        </p>
      )}
      {status === 'saved' && (
        <p style={{
          margin: '6px 0 0',
          fontSize: 'var(--text-xs)',
          color: 'var(--color-status-success)',
        }}>
          Escalation emails will be sent to {savedEmail}
        </p>
      )}
    </div>
  );
}

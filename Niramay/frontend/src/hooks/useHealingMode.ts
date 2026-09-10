/**
 * useHealingMode — Polls /api/v1/healing/mode every 3s.
 * Provides setMode() to call POST /api/v1/healing/mode.
 * Also fetches pending manual actions for the ManualHealingPanel.
 * Used by HealingModeModal and ManualHealingPanel (Feature 6).
 */

import { useState, useEffect, useCallback } from 'react';
import type { HealingMode, PendingHealingAction } from '../designSystem';

export function useHealingMode() {
  const [healingMode, setHealingModeState] = useState<HealingMode>({ mode: null, set_at: null });
  const [pendingActions, setPendingActions] = useState<PendingHealingAction[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMode = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/healing/mode');
      if (res.ok) setHealingModeState(await res.json());
    } catch { /* silent */ }
  }, []);

  const fetchPending = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/healing/pending');
      if (res.ok) setPendingActions(await res.json());
    } catch { /* silent */ }
  }, []);

  /** POST /api/v1/healing/mode — sets mode and updates local state immediately. */
  const setMode = useCallback(async (mode: 'autonomous' | 'manual') => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/healing/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (res.ok) {
        const data: HealingMode = await res.json();
        setHealingModeState(data);
      }
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  /** POST /api/v1/healing/pending/{id}/decision — approve or reject a pending action. */
  const decideAction = useCallback(async (actionId: string, decision: 'approve' | 'reject') => {
    try {
      await fetch(`/api/v1/healing/pending/${actionId}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      });
      await fetchPending();
    } catch { /* silent */ }
  }, [fetchPending]);

  useEffect(() => {
    fetchMode();
    fetchPending();
    const id = setInterval(() => { fetchMode(); fetchPending(); }, 3000);
    return () => clearInterval(id);
  }, [fetchMode, fetchPending]);

  return { healingMode, pendingActions, loading, setMode, decideAction, refetch: fetchMode };
}

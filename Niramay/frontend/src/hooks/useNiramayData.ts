/**
 * useNiramayData — Shared data fetching hook for all Niramay pages.
 * Polls observation logs, anomaly data, healing actions, and escalations.
 *
 * Uses server-side fingerprints to detect actual data changes and avoid
 * phantom updates (re-rendering unchanged data with animations).
 *
 * Also provides useLogHistory, useAnomalyHistory, usePipelineStage,
 * useCraveConnectionStatus, useConsumerControl, and useHealingToggle.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import type { ObservationLog, AnomalyLog, HealingAction, SystemStats, EscalationAlert, IncidentReport } from '../designSystem';

// Empty string routes all requests through the Vite proxy (/api → niramay-backend:8000).
// Never use VITE_API_URL here — the browser cannot resolve the docker container hostname.
const API = '';

export interface NiramayData {
  logs: ObservationLog[];
  anomalies: AnomalyLog[];
  healingActions: HealingAction[];
  escalations: EscalationAlert[];
  incidentReports: IncidentReport[];
  stats: SystemStats | null;
  isLive: boolean;
  setIsLive: (v: boolean) => void;
  lastRefresh: Date;
  loading: boolean;
  fetchData: () => void;
  metrics: {
    totalRequests: number;
    successRate: string;
    avgLatency: string;
    activeAnomalies: number;
    totalHealed: number;
  };
}

export function useNiramayData(): NiramayData {
  const [logs, setLogs] = useState<ObservationLog[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyLog[]>([]);
  const [healingActions, setHealingActions] = useState<HealingAction[]>([]);
  const [escalations, setEscalations] = useState<EscalationAlert[]>([]);
  const [incidentReports, setIncidentReports] = useState<IncidentReport[]>([]);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [isLive, setIsLive] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // Fingerprint refs — only update state when data actually changes
  const logsFingerprintRef = useRef<string>('');
  const anomaliesFingerprintRef = useRef<string>('');
  const healingFingerprintRef = useRef<string>('');

  const fetchData = useCallback(async () => {
    try {
      const [a, b, c, d, e, f] = await Promise.allSettled([
        axios.get(`${API}/api/v1/observation/logs?limit=50`),
        axios.get(`${API}/api/v1/detection/anomalies?limit=30`),
        axios.get(`${API}/api/v1/healing/actions?limit=30`),
        axios.get(`${API}/api/v1/stats`),
        axios.get(`${API}/api/v1/escalations?limit=20`),
        axios.get(`${API}/api/v1/incident/reports?limit=20`),
      ]);

      // Logs — only update if fingerprint changed
      if (a.status === 'fulfilled' && a.value.data) {
        const resp = a.value.data;
        // Handle both old (array) and new ({logs, fingerprint}) formats
        if (Array.isArray(resp)) {
          setLogs(resp);
        } else if (resp.fingerprint && resp.fingerprint !== logsFingerprintRef.current) {
          logsFingerprintRef.current = resp.fingerprint;
          setLogs(resp.logs || []);
        }
      }

      // Anomalies — only update if fingerprint changed
      if (b.status === 'fulfilled' && b.value.data) {
        const resp = b.value.data;
        if (Array.isArray(resp)) {
          setAnomalies(resp);
        } else if (resp.fingerprint && resp.fingerprint !== anomaliesFingerprintRef.current) {
          anomaliesFingerprintRef.current = resp.fingerprint;
          setAnomalies(resp.anomalies || []);
        }
      }

      // Healing actions — only update if fingerprint changed
      if (c.status === 'fulfilled' && c.value.data) {
        const resp = c.value.data;
        if (Array.isArray(resp)) {
          setHealingActions(resp);
        } else if (resp.fingerprint && resp.fingerprint !== healingFingerprintRef.current) {
          healingFingerprintRef.current = resp.fingerprint;
          setHealingActions(resp.actions || []);
        }
      }

      if (d.status === 'fulfilled' && d.value.data) {
        setStats(d.value.data);
      }
      if (e.status === 'fulfilled' && Array.isArray(e.value.data)) {
        setEscalations(e.value.data);
      }
      if (f.status === 'fulfilled' && Array.isArray(f.value.data)) {
        setIncidentReports(f.value.data);
      }

      setLastRefresh(new Date());
      setLoading(false);
    } catch (err) {
      console.error("Fetch data error:", err);
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (isLive) timerRef.current = setInterval(fetchData, 3000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isLive, fetchData]);

  const tot = logs.length;
  const fail = logs.filter(l => l.status_code >= 400).length;
  const avg = tot > 0 ? (logs.reduce((s, l) => s + (l.response_time_ms ?? 0), 0) / tot).toFixed(0) : '—';
  const rate = tot > 0 ? ((1 - fail / tot) * 100).toFixed(1) : '—';

  return {
    logs,
    anomalies,
    healingActions,
    escalations,
    incidentReports,
    stats,
    isLive,
    setIsLive,
    lastRefresh,
    loading,
    fetchData,
    metrics: {
      totalRequests: stats?.total_logs || 0,
      successRate: stats?.health_score !== undefined ? stats.health_score.toFixed(1) : '100.0',
      avgLatency: avg !== '—' ? `${avg}ms` : '—',
      activeAnomalies: stats?.total_anomalies || 0,
      totalHealed: healingActions.length,
    },
  };
}


export function usePipelineStage(
    enabled: boolean = true
) {
    const [stage, setStage] = useState<{
        stage: string;
        message: string;
        timestamp: string | null;
        stale?: boolean;
        service?: string;
        severity?: string;
        failure_tag?: string;
        recommended_action?: string;
        healing_action?: string;
        status?: string;
        time_to_heal?: number;
    } | null>(null);

    useEffect(() => {
        if (!enabled) return;
        const poll = async () => {
            try {
                const res = await fetch(
                    "/api/v1/pipeline/stage"
                );
                if (res.ok) {
                    const data = await res.json();
                    setStage(data);
                }
            } catch {}
        };
        poll();
        const interval = setInterval(poll, 2000);
        return () => clearInterval(interval);
    }, [enabled]);

    return stage;
}


/**
 * useCraveConnectionStatus — Detects whether CRAVE is actively
 * publishing logs by comparing total_log counts across polls.
 * Returns true when the log count is increasing.
 */
export function useCraveConnectionStatus(): boolean {
  const [connected, setConnected] = useState(false);
  const lastCountRef = useRef(0);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch('/api/v1/stats');
        if (res.ok) {
          const data = await res.json();
          const count: number = data.total_logs || 0;
          setConnected(count > lastCountRef.current);
          lastCountRef.current = count;
        }
      } catch {}
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, []);

  return connected;
}


/**
 * useConsumerControl — Provides consumer start/stop/status control
 * and live consumer event log.
 */
export interface ConsumerStatus {
  running: boolean;
  connected: boolean;
  messages_consumed: number;
  last_message_at: string | null;
  started_at: string | null;
  error: string | null;
  thread_alive: boolean;
}

export interface ConsumerEvent {
  type: string;
  message: string;
  timestamp: string;
  messages_consumed: number;
}

export function useConsumerControl() {
  const [status, setStatus] = useState<ConsumerStatus>({
    running: false,
    connected: false,
    messages_consumed: 0,
    last_message_at: null,
    started_at: null,
    error: null,
    thread_alive: false,
  });
  const [events, setEvents] = useState<ConsumerEvent[]>([]);
  const [loading, setLoading] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/consumer/status');
      if (res.ok) setStatus(await res.json());
    } catch {}
  }, []);

  const refreshEvents = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/consumer/events?limit=50');
      if (res.ok) setEvents(await res.json());
    } catch {}
  }, []);

  const startConsumer = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/consumer/start', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setStatus(data.status);
      }
    } catch (e) {
      console.error('Failed to start consumer:', e);
    }
    setLoading(false);
  }, []);

  const stopConsumer = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/consumer/stop', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setStatus(data.status);
      }
    } catch (e) {
      console.error('Failed to stop consumer:', e);
    }
    setLoading(false);
  }, []);

  // Poll status and events
  useEffect(() => {
    refreshStatus();
    refreshEvents();
    const interval = setInterval(() => {
      refreshStatus();
      refreshEvents();
    }, 3000);
    return () => clearInterval(interval);
  }, [refreshStatus, refreshEvents]);

  return {
    status,
    events,
    loading,
    startConsumer,
    stopConsumer,
    refreshStatus,
    refreshEvents,
  };
}


/**
 * useHealingToggle — Controls whether healing actions are executed.
 */
export function useHealingToggle() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(false);

  const refreshState = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/healing/enabled');
      if (res.ok) {
        const data = await res.json();
        setEnabled(data.enabled);
      }
    } catch {}
  }, []);

  const toggle = useCallback(async (newValue?: boolean) => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/healing/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newValue ?? !enabled }),
      });
      if (res.ok) {
        const data = await res.json();
        setEnabled(data.enabled);
      }
    } catch (e) {
      console.error('Failed to toggle healing:', e);
    }
    setLoading(false);
  }, [enabled]);

  useEffect(() => {
    refreshState();
    const interval = setInterval(refreshState, 5000);
    return () => clearInterval(interval);
  }, [refreshState]);

  return { enabled, loading, toggle };
}


/**
 * useLogHistory — Fetches historical logs from OpenSearch.
 * Refreshes every 30 seconds.
 */
export function useLogHistory(service?: string) {
  const [logs, setLogs] = useState<ObservationLog[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (service) params.set('service', service);
      params.set('limit', '500');
      const res = await axios.get(`${API}/api/v1/observation/logs/history?${params}`);
      if (Array.isArray(res.data)) setLogs(res.data);
    } catch (err) {
      console.error('Log history fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [service]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  useEffect(() => {
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, [fetchHistory]);

  return { logs, loading, refetch: fetchHistory };
}


/**
 * useAnomalyHistory — Fetches historical anomalies from OpenSearch.
 * Refreshes every 30 seconds.
 */
export function useAnomalyHistory(service?: string) {
  const [anomalies, setAnomalies] = useState<AnomalyLog[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (service) params.set('service', service);
      params.set('limit', '200');
      const res = await axios.get(`${API}/api/v1/detection/anomalies/history?${params}`);
      if (Array.isArray(res.data)) setAnomalies(res.data);
    } catch (err) {
      console.error('Anomaly history fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [service]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  useEffect(() => {
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, [fetchHistory]);

  return { anomalies, loading, refetch: fetchHistory };
}

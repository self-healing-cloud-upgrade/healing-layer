/**
 * Niramay Design System v2.0
 *
 * Cyber-dark + Warm-light dual theme.
 * Space Grotesk display, Inter body, JetBrains Mono code.
 * data-theme="light|dark" on <html>. Luxon dates. AOS scroll.
 * All data types and API contracts preserved exactly.
 */

import {
  createContext, useContext, useState, useCallback, useEffect,
  type ReactNode, createElement,
} from 'react';
import { DateTime } from 'luxon';
import AOS from 'aos';

/* ═══════════════════════════════════════════════════════════════════
   THEME CONTEXT
   ═══════════════════════════════════════════════════════════════════ */

interface ThemeCtx {
  isDark: boolean;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeCtx>({
  isDark: true,
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isDark, setIsDark] = useState(() => {
    if (typeof window === 'undefined') return true;
    const stored = localStorage.getItem('niramay-theme');
    if (stored) return stored === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  const toggleTheme = useCallback(() => {
    setIsDark(prev => {
      const next = !prev;
      const theme = next ? 'dark' : 'light';
      localStorage.setItem('niramay-theme', theme);

      document.documentElement.classList.add('theme-transitioning');
      document.documentElement.setAttribute('data-theme', theme);

      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', next ? '#0A0E17' : '#F5F2ED');

      setTimeout(() => {
        document.documentElement.classList.remove('theme-transitioning');
      }, 400);

      return next;
    });
  }, []);

  useEffect(() => {
    const theme = isDark ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', isDark ? '#0A0E17' : '#F5F2ED');
  }, [isDark]);

  useEffect(() => {
    AOS.init({
      duration: 700,
      easing: 'ease-out-quart',
      once: true,
      offset: 60,
      delay: 0,
    });
  }, []);

  return createElement(
    ThemeContext.Provider,
    { value: { isDark, toggleTheme } },
    children
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

/* ═══════════════════════════════════════════════════════════════════
   DATA TYPES — Aligned with Redis flat JSON structures
   ═══════════════════════════════════════════════════════════════════ */

export interface ObservationLog {
  timestamp: string;
  service: string;
  endpoint: string;
  method: string;
  status_code: number;
  response_time_ms: number;
  failure_tag: string;
  request_id?: string;
  // Extra fields returned by the normalizer — useful for diagnostics
  incomplete_fields?: string[];
  is_malformed?: boolean;
  is_timestamp_assigned?: boolean;
  raw?: string;
}

export interface AnomalyLog {
  detection_id: string;
  timestamp: string;
  service: string;
  endpoint: string;
  method: string;
  status_code: number;
  response_time_ms: number;
  failure_tag: string;
  anomaly_score: number;
  anomaly_reasons: string[];
  engines_triggered: string[];
  severity: 'low' | 'medium' | 'high' | 'critical';
  is_anomaly: boolean;
  requires_llm: boolean;
  ai_analysis?: {
    root_cause: string;
    confidence: number;
    suggested_action: string;
    analysis_type?: string;
    skipped?: boolean;
    reason?: string;
  };
  healing?: HealingAction;
}

export interface SystemStats {
  total_logs: number;
  total_anomalies: number;
  health_score: number;
  by_endpoint: Record<string, number>;
  by_type: Record<string, number>;
}

export interface HealingAction {
  healing_action: string;
  status: string;
  timestamp: string;
  message: string;
  verification_status: string;
  // Fields added to match full API response (dispatcher worker)
  alert_id?: string;
  detection_id?: string;
  service?: string;
  endpoint?: string;
  failure_tag?: string;
  recommended_action?: string;
  container_restarted?: string | null;
  scenarios_disabled?: string[];
  error?: string | null;
  executed_at?: string;
  heal_endpoint_called?: boolean;
  retry_count?: number;
  // K3s Phase 2 result fields
  k3s_deployment?: string;
  k3s_namespace?: string;
  new_replicas?: number;
  previous_replicas?: number;
  rolled_back_to?: string;
  original_replicas?: number;
  circuit_duration?: number;
  throttled_replicas?: number;
  duration_seconds?: number;
  redis_pod?: string;
}

export interface IncidentReport {
  detection_id: string;
  timestamp: string;
  service: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  human_report: string;
  machine_alert: any;
  verification_status: string;
}

export interface EscalationAlert {
  type: string;
  service: string;
  endpoint: string;
  failure_type: string;  // Matches backend schemas.py EscalationAlertResponse
  attempts: number;
  healing_actions_tried: string[];
  outcomes: string[];
  timestamp: string;
  message: string;
}

/* ═══════════════════════════════════════════════════════════════════
   UTILITIES — Luxon-based
   ═══════════════════════════════════════════════════════════════════ */

export function timeAgo(ts: string): string {
  const dt = DateTime.fromISO(ts);
  if (!dt.isValid) {
    const d = Date.now() - new Date(ts).getTime();
    if (d < 1000) return 'now';
    if (d < 60000) return `${Math.floor(d / 1000)}s`;
    if (d < 3600000) return `${Math.floor(d / 60000)}m`;
    return `${Math.floor(d / 3600000)}h`;
  }
  return dt.toRelative({ style: 'short' }) || 'now';
}

export function formatTimestamp(ts: string): string {
  const dt = DateTime.fromISO(ts);
  if (!dt.isValid) return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return dt.toFormat('HH:mm:ss');
}

export function statusDotClass(code: number): string {
  if (code >= 500) return 'error';
  if (code >= 400) return 'warning';
  if (code >= 200 && code < 300) return 'success';
  return 'neutral';
}

export function methodLabel(m: string): string {
  return m.toUpperCase();
}

/* ═══════════════════════════════════════════════════════════════════
   AI RECOMMENDATIONS — unchanged
   ═══════════════════════════════════════════════════════════════════ */

export const AI_RECOMMENDATIONS = [
  {
    id: 1,
    severity: 'high' as const,
    title: 'Database connection pool exhaustion predicted in ~12 min',
    desc: 'Connection pool usage trending upward at 8.3%/min.',
    action: 'Pre-scale connection pool',
  },
  {
    id: 2,
    severity: 'medium' as const,
    title: 'Anomaly cluster detected on /api/v1/orders',
    desc: 'Latency correlates with payment gateway degradation.',
    action: 'Enable circuit breaker',
  },
  {
    id: 3,
    severity: 'low' as const,
    title: '34% of retry_request actions are redundant',
    desc: 'Endpoints with >95% eventual success resolve naturally.',
    action: 'Adjust retry threshold',
  },
];

/* ═══════════════════════════════════════════════════════════════════
   RIPPLE EFFECT UTILITY
   ═══════════════════════════════════════════════════════════════════ */

export function createRipple(e: React.MouseEvent<HTMLElement>) {
  const element = e.currentTarget;
  const rect = element.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  const x = e.clientX - rect.left - size / 2;
  const y = e.clientY - rect.top - size / 2;

  const ripple = document.createElement('span');
  ripple.className = 'ripple';
  ripple.style.width = ripple.style.height = `${size}px`;
  ripple.style.left = `${x}px`;
  ripple.style.top = `${y}px`;

  element.appendChild(ripple);
  setTimeout(() => ripple.remove(), 600);
}

/* ═══════════════════════════════════════════════════════════════════
   NEW DATA TYPES — Features 1–6
   ═══════════════════════════════════════════════════════════════════ */

/** Feature 1 — Raw log entry from crave-raw-logs */
export interface RawLogHit {
  timestamp: string;
  source: string;
  message: string;
  level: string;
  traceId: string;
  _raw: Record<string, unknown>;
}

/** Feature 1 — Normalized log entry from crave-normalized-logs */
export interface NormalizedLogHit {
  timestamp: string;
  service: string;
  endpoint: string;
  method: string;
  status_code: number;
  response_time_ms: number;
  failure_tag: string;
  request_id?: string;
  anomaly_score?: number;
  is_malformed?: boolean;
  raw?: string;
}

/** Feature 1 — Paginated log response envelope */
export interface LogPage<T> {
  total: number;
  page: number;
  size: number;
  hits: T[];
}

/** Feature 2 — Artifact card data */
export interface ArtifactCard {
  key: 'raw-logs' | 'anomaly-records' | 'incident-reports' | 'heal-report';
  index: string;
  count: number;
  last_updated: string | null;
}

/** Feature 3 — Report entry */
export interface Report {
  report_id: string;
  report_type: 'incident_summary' | 'heal_summary' | 'full_pipeline';
  date_from: string;
  date_to: string;
  severities: string[];
  format: 'pdf' | 'json' | 'csv';
  status: 'pending' | 'ready' | 'failed';
  generated_at: string | null;
  row_count: number | null;
  created_at: string;
}

/** Feature 4 — Pipeline event (from /api/v1/pipeline/events) */
export interface PipelineEvent {
  event_type: string;
  stage: string;
  timestamp: string;
  message: string;
}

/** Feature 6 — Healing mode state */
export interface HealingMode {
  mode: 'autonomous' | 'manual' | null;
  set_at: string | null;
}

/** Feature 6 — Pending manual healing action */
export interface PendingHealingAction {
  action_id: string;
  healing_action: string;
  service?: string;
  endpoint?: string;
  failure_tag?: string;
  timestamp: string;
  message: string;
}

/** Feature 5b — OpenSearch search result hit */
export interface SearchHit {
  _score: number;
  timestamp: string;
  snippet: string;
  _source: Record<string, unknown>;
}

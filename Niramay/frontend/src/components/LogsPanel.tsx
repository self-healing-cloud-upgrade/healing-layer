/**
 * LogsPanel — Feature 1: Dual-tab log viewer.
 *
 * Tab A — Raw Logs     (GET /api/v1/logs/raw)
 * Tab B — Normalized Logs (GET /api/v1/logs/normalized)
 *
 * Tab state is synced to URL param ?logsTab=raw|normalized.
 * Each tab has: keyword search (300ms debounce), Level multi-select dropdown,
 * time-range picker, paginated row table, and inline JSON detail drawer.
 * Normalized tab adds Anomaly Score column with colour gradient.
 * "Open in OpenSearch" button deep-links to OpenSearch Dashboards.
 */

import { useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useRawLogs, useNormalizedLogs } from '../hooks/useLogs';
import type { LogFilters, TimeRange } from '../hooks/useLogs';
import type { RawLogHit, NormalizedLogHit } from '../designSystem';
import { formatTimestamp } from '../designSystem';

const LEVELS = ['INFO', 'WARN', 'ERROR'];
const TIME_RANGE_OPTIONS: { label: string; value: TimeRange }[] = [
  { label: 'Last 1h', value: '1h' },
  { label: 'Last 6h', value: '6h' },
  { label: 'Last 24h', value: '24h' },
  { label: 'Custom', value: 'custom' },
];

const OS_DASHBOARDS_URL = import.meta.env.VITE_OPENSEARCH_DASHBOARDS_URL ?? 'http://localhost:5601';

const DEFAULT_FILTERS: LogFilters = {
  keyword: '', levels: [], timeRange: '1h', customFrom: '', customTo: '',
};

/** Anomaly score → CSS colour */
function scoreColor(score: number, threshold = 0.4): string {
  if (score >= threshold * 1.5) return 'var(--color-status-error)';
  if (score >= threshold) return 'var(--color-status-warning)';
  return 'var(--color-text-tertiary)';
}

function levelBadge(level: string) {
  const map: Record<string, string> = {
    ERROR: 'badge-error', WARN: 'badge-warning', INFO: 'badge-neutral',
  };
  return map[level.toUpperCase()] ?? 'badge-neutral';
}

function FilterBar({ filters, onChange }: { filters: LogFilters; onChange: (f: LogFilters) => void }) {
  const [levelOpen, setLevelOpen] = useState(false);

  return (
    <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center', padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--color-border-subtle)' }}>
      {/* Keyword */}
      <input
        id="log-keyword-search"
        type="search"
        placeholder="Search logs…"
        value={filters.keyword}
        onChange={e => onChange({ ...filters, keyword: e.target.value })}
        aria-label="Search logs by keyword"
        style={{
          flex: '1 1 180px', padding: '5px 10px',
          background: 'var(--color-bg-sunken)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-md)',
          color: 'var(--color-text-primary)',
          fontSize: 'var(--text-sm)',
          outline: 'none',
        }}
      />

      {/* Level multi-select */}
      <div style={{ position: 'relative' }}>
        <button
          id="log-level-filter"
          onClick={() => setLevelOpen(v => !v)}
          aria-haspopup="listbox"
          aria-expanded={levelOpen}
          aria-label="Filter by log level"
          style={{
            padding: '5px 10px', borderRadius: 'var(--radius-md)',
            background: 'var(--color-bg-sunken)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-secondary)',
            fontSize: 'var(--text-sm)', cursor: 'pointer',
          }}
        >
          Level {filters.levels.length > 0 ? `(${filters.levels.length})` : ''}
        </button>
        {levelOpen && (
          <div
            role="listbox"
            aria-multiselectable="true"
            aria-label="Log level options"
            style={{
              position: 'absolute', top: '110%', left: 0, zIndex: 100,
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border-default)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-2)',
              minWidth: 120,
              boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
            }}
          >
            {LEVELS.map(lv => (
              <label key={lv} role="option" aria-selected={filters.levels.includes(lv)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                <input
                  type="checkbox"
                  checked={filters.levels.includes(lv)}
                  onChange={e => onChange({
                    ...filters,
                    levels: e.target.checked ? [...filters.levels, lv] : filters.levels.filter(l => l !== lv),
                  })}
                />
                {lv}
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Time range */}
      <select
        id="log-time-range"
        value={filters.timeRange}
        onChange={e => onChange({ ...filters, timeRange: e.target.value as TimeRange })}
        aria-label="Select time range"
        style={{
          padding: '5px 10px', borderRadius: 'var(--radius-md)',
          background: 'var(--color-bg-sunken)',
          border: '1px solid var(--color-border-subtle)',
          color: 'var(--color-text-secondary)',
          fontSize: 'var(--text-sm)', cursor: 'pointer',
        }}
      >
        {TIME_RANGE_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {filters.timeRange === 'custom' && (
        <>
          <input
            type="datetime-local"
            id="log-custom-from"
            value={filters.customFrom}
            onChange={e => onChange({ ...filters, customFrom: e.target.value })}
            aria-label="Custom start time"
            style={{ padding: '4px 8px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-sunken)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)', fontSize: 12 }}
          />
          <input
            type="datetime-local"
            id="log-custom-to"
            value={filters.customTo}
            onChange={e => onChange({ ...filters, customTo: e.target.value })}
            aria-label="Custom end time"
            style={{ padding: '4px 8px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-sunken)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)', fontSize: 12 }}
          />
        </>
      )}
    </div>
  );
}

function RawLogsTable({ filters }: { filters: LogFilters }) {
  const [page, setPage] = useState(1);
  const { data, loading } = useRawLogs(filters, page);
  const [expanded, setExpanded] = useState<string | null>(null);
  const totalPages = Math.ceil(data.total / data.size) || 1;

  const openSearch = useCallback(() => {
    const q = filters.keyword ? encodeURIComponent(filters.keyword) : '*';
    window.open(`${OS_DASHBOARDS_URL}/app/discover#/?_q=${q}&_a=(index:crave-raw-logs)`, '_blank', 'noopener');
  }, [filters.keyword]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 'var(--space-2) var(--space-4)' }}>
        <button
          id="raw-logs-opensearch-btn"
          onClick={openSearch}
          aria-label="Open raw logs in OpenSearch Dashboards"
          className="btn-ghost"
          style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M6 3H3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-3" />
            <path d="M10 1h5v5" /><path d="M15 1 8 8" />
          </svg>
          Open in OpenSearch
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>Loading…</div>
      ) : data.hits.length === 0 ? (
        <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>No raw logs found.</div>
      ) : (
        <div>
          {data.hits.map((row, i) => (
            <div key={`${row.traceId}-${i}`}>
              <div
                className="row-interactive"
                onClick={() => setExpanded(expanded === row.traceId ? null : row.traceId)}
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && setExpanded(expanded === row.traceId ? null : row.traceId)}
                aria-expanded={expanded === row.traceId}
                style={{
                  display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                  padding: 'var(--space-2) var(--space-4)',
                  cursor: 'pointer', borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-xs)',
                }}
              >
                <span style={{ color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)', width: 80, flexShrink: 0 }}>
                  {formatTimestamp(row.timestamp)}
                </span>
                <span className={`badge ${levelBadge(row.level)}`} style={{ flexShrink: 0, fontSize: 9 }}>{row.level}</span>
                <span style={{ color: 'var(--color-text-tertiary)', width: 100, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.source}</span>
                <span style={{ flex: 1, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.message}</span>
                <span style={{ color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 9, width: 80, flexShrink: 0, textAlign: 'right' }}>{row.traceId.slice(0, 8)}</span>
              </div>
              <AnimatePresence>
                {expanded === row.traceId && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    style={{ overflow: 'hidden' }}
                  >
                    <pre style={{
                      margin: 0, padding: 'var(--space-3) var(--space-4)',
                      background: 'var(--color-bg-sunken)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 11, lineHeight: 1.6,
                      color: 'var(--color-text-secondary)',
                      fontFamily: 'var(--font-mono)',
                      overflowX: 'auto',
                    }}>
                      {JSON.stringify(row._raw, null, 2)}
                    </pre>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-3)' }}>
        <button id="raw-logs-prev" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="btn-ghost" aria-label="Previous page" style={{ fontSize: 'var(--text-xs)' }}>← Prev</button>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Page {page} / {totalPages} ({data.total} total)</span>
        <button id="raw-logs-next" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="btn-ghost" aria-label="Next page" style={{ fontSize: 'var(--text-xs)' }}>Next →</button>
      </div>
    </div>
  );
}

function NormalizedLogsTable({ filters }: { filters: LogFilters }) {
  const [page, setPage] = useState(1);
  const threshold = 0.4;
  const { data, loading } = useNormalizedLogs(filters, page, 50, threshold);
  const [expanded, setExpanded] = useState<number | null>(null);
  const totalPages = Math.ceil(data.total / data.size) || 1;

  const openSearch = useCallback(() => {
    const q = filters.keyword ? encodeURIComponent(filters.keyword) : '*';
    window.open(`${OS_DASHBOARDS_URL}/app/discover#/?_q=${q}&_a=(index:crave-normalized-logs)`, '_blank', 'noopener');
  }, [filters.keyword]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 'var(--space-2) var(--space-4)' }}>
        <button
          id="normalized-logs-opensearch-btn"
          onClick={openSearch}
          aria-label="Open normalized logs in OpenSearch Dashboards"
          className="btn-ghost"
          style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M6 3H3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-3" />
            <path d="M10 1h5v5" /><path d="M15 1 8 8" />
          </svg>
          Open in OpenSearch
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>Loading…</div>
      ) : data.hits.length === 0 ? (
        <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>No normalized logs found.</div>
      ) : (
        <div>
          {(data.hits as NormalizedLogHit[]).map((row, i) => {
            const isAnomalous = (row.anomaly_score ?? 0) >= threshold;
            return (
              <div key={i}>
                <div
                  className="row-interactive"
                  onClick={() => setExpanded(expanded === i ? null : i)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && setExpanded(expanded === i ? null : i)}
                  aria-expanded={expanded === i}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                    padding: 'var(--space-2) var(--space-4)',
                    cursor: 'pointer', borderRadius: 'var(--radius-sm)',
                    fontSize: 'var(--text-xs)',
                    borderLeft: isAnomalous ? `3px solid ${scoreColor(row.anomaly_score ?? 0, threshold)}` : '3px solid transparent',
                  }}
                >
                  <span style={{ color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)', width: 80, flexShrink: 0 }}>
                    {formatTimestamp(row.timestamp)}
                  </span>
                  <span style={{ color: scoreColor(row.anomaly_score ?? 0, threshold), fontFamily: 'var(--font-mono)', width: 44, flexShrink: 0, fontWeight: isAnomalous ? 600 : 400 }}>
                    {row.anomaly_score !== undefined ? row.anomaly_score.toFixed(2) : '—'}
                  </span>
                  <span className={`badge ${row.status_code >= 500 ? 'badge-error' : row.status_code >= 400 ? 'badge-warning' : 'badge-neutral'}`} style={{ flexShrink: 0, fontSize: 9 }}>
                    {row.status_code}
                  </span>
                  <span style={{ color: 'var(--color-text-tertiary)', width: 80, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.service}</span>
                  <span style={{ flex: 1, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.endpoint}</span>
                  <span style={{ color: 'var(--color-text-tertiary)', width: 50, flexShrink: 0, textAlign: 'right' }}>{row.response_time_ms}ms</span>
                </div>
                <AnimatePresence>
                  {expanded === i && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      style={{ overflow: 'hidden' }}
                    >
                      <pre style={{
                        margin: 0, padding: 'var(--space-3) var(--space-4)',
                        background: 'var(--color-bg-sunken)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: 11, lineHeight: 1.6,
                        color: 'var(--color-text-secondary)',
                        fontFamily: 'var(--font-mono)',
                        overflowX: 'auto',
                      }}>
                        {JSON.stringify(row, null, 2)}
                      </pre>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-3)' }}>
        <button id="norm-logs-prev" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="btn-ghost" aria-label="Previous page" style={{ fontSize: 'var(--text-xs)' }}>← Prev</button>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Page {page} / {totalPages} ({data.total} total)</span>
        <button id="norm-logs-next" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="btn-ghost" aria-label="Next page" style={{ fontSize: 'var(--text-xs)' }}>Next →</button>
      </div>
    </div>
  );
}

export default function LogsPanel() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = (searchParams.get('logsTab') ?? 'raw') as 'raw' | 'normalized';
  const [collapsed, setCollapsed] = useState(false);
  const [filters, setFilters] = useState<LogFilters>(DEFAULT_FILTERS);

  const setTab = useCallback((t: 'raw' | 'normalized') => {
    setSearchParams(p => { p.set('logsTab', t); return p; });
  }, [setSearchParams]);

  return (
    <div
      className="glass card-glass"
      style={{ marginBottom: 'var(--space-6)', overflow: 'hidden' }}
      data-aos="fade-up"
    >
      {/* Panel header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: 'var(--space-4) var(--space-6)',
        borderBottom: collapsed ? 'none' : '1px solid var(--color-border-subtle)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
          <button
            id="logs-collapse-toggle"
            onClick={() => setCollapsed(v => !v)}
            className="btn-ghost"
            aria-expanded={!collapsed}
            aria-controls="logs-panel-body"
            aria-label={collapsed ? 'Expand logs panel' : 'Collapse logs panel'}
            style={{ padding: 2 }}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
              style={{ transform: collapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 200ms' }}>
              <polyline points="2,5 8,11 14,5" />
            </svg>
          </button>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-md)', color: 'var(--color-text-primary)' }}>
            Logs
          </span>
        </div>

        {/* Tab switcher */}
        {!collapsed && (
          <div style={{
            display: 'flex', borderRadius: 'var(--radius-md)',
            background: 'var(--color-bg-sunken)',
            border: '1px solid var(--color-border-subtle)',
            overflow: 'hidden',
          }}>
            {(['raw', 'normalized'] as const).map(t => (
              <button
                key={t}
                id={`logs-tab-${t}`}
                onClick={() => setTab(t)}
                aria-pressed={tab === t}
                style={{
                  padding: '4px 14px',
                  background: tab === t ? 'var(--color-accent-primary)' : 'transparent',
                  color: tab === t ? '#fff' : 'var(--color-text-secondary)',
                  border: 'none', fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
                  transition: 'all 150ms',
                  textTransform: 'capitalize',
                }}
              >
                {t === 'raw' ? 'Raw Logs' : 'Normalized'}
              </button>
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {!collapsed && (
          <motion.div
            id="logs-panel-body"
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <FilterBar filters={filters} onChange={setFilters} />
            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              {tab === 'raw' ? <RawLogsTable filters={filters} /> : <NormalizedLogsTable filters={filters} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

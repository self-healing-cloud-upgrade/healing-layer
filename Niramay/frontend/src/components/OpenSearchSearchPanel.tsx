/**
 * OpenSearchSearchPanel — Feature 5b.
 *
 * Full-text search panel that calls GET /api/v1/opensearch/search.
 * Allows selecting the target index (normalized logs, anomalies, incidents, healed).
 * Results show score, timestamp, and a 200-char snippet.
 * "View in OpenSearch" button deep-links to Dashboards.
 */

import { useState, useRef, useCallback } from 'react';
import type { SearchHit } from '../designSystem';

const OS_DASHBOARDS_URL = import.meta.env.VITE_OPENSEARCH_DASHBOARDS_URL ?? 'http://localhost:5601';

const INDEX_OPTIONS = [
  { label: 'Normalized Logs',   value: 'crave-normalized-logs' },
  { label: 'Anomaly Records',   value: 'crave-anomaly-records' },
  { label: 'Incident Reports',  value: 'crave-incident-reports' },
  { label: 'Heal Reports',      value: 'crave-healed-reports' },
];

export default function OpenSearchSearchPanel() {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState('crave-normalized-logs');
  const [results, setResults] = useState<SearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const search = useCallback(async (q: string, idx: string) => {
    if (!q.trim()) { setResults([]); setTotal(0); return; }
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ q, index: idx, size: '20' });
      const res = await fetch(`/api/v1/opensearch/search?${params}`);
      if (res.ok) {
        const data = await res.json();
        setResults(data.hits ?? []);
        setTotal(data.total ?? 0);
      } else {
        setError('Search failed. Is OpenSearch running?');
      }
    } catch {
      setError('Cannot reach backend.');
    }
    setLoading(false);
  }, []);

  const handleInput = (q: string) => {
    setQuery(q);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(q, index), 400);
  };

  const openInDashboards = () => {
    const url = `${OS_DASHBOARDS_URL}/app/discover#/?_q=${encodeURIComponent(query)}&_a=(index:${index})`;
    window.open(url, '_blank', 'noopener');
  };

  const formatTime = (ts: string) => {
    try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
    catch { return ts; }
  };

  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase', marginBottom: 'var(--space-2)' }}>
        OpenSearch
      </div>

      {/* Search row */}
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <input
          id="opensearch-query-input"
          type="search"
          value={query}
          onChange={e => handleInput(e.target.value)}
          placeholder="Search across OpenSearch…"
          aria-label="Full-text OpenSearch search"
          style={{
            flex: 1, padding: '7px 12px',
            background: 'var(--color-bg-sunken)',
            border: '1px solid var(--color-border-default)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--color-text-primary)',
            fontSize: 'var(--text-sm)',
            outline: 'none',
          }}
        />
        <select
          id="opensearch-index-select"
          value={index}
          onChange={e => { setIndex(e.target.value); search(query, e.target.value); }}
          aria-label="Select OpenSearch index"
          style={{
            padding: '7px 10px',
            background: 'var(--color-bg-sunken)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--color-text-secondary)',
            fontSize: 'var(--text-xs)',
            cursor: 'pointer',
          }}
        >
          {INDEX_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {query && (
          <button
            id="opensearch-dashboard-btn"
            onClick={openInDashboards}
            className="btn-ghost"
            aria-label="View results in OpenSearch Dashboards"
            style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M6 3H3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-3" />
              <path d="M10 1h5v5" /><path d="M15 1 8 8" />
            </svg>
            Open
          </button>
        )}
      </div>

      {/* Status */}
      {loading && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', marginBottom: 'var(--space-2)' }}>Searching…</div>}
      {error && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-status-error)', marginBottom: 'var(--space-2)' }}>{error}</div>}
      {!loading && results.length > 0 && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', marginBottom: 'var(--space-2)' }}>
          {total} results
        </div>
      )}

      {/* Results */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {results.map((hit, i) => (
          <div
            key={i}
            className="row-interactive"
            style={{ borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-3)', cursor: 'default' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-text-tertiary)' }}>
                {formatTime(hit.timestamp)}
              </span>
              <span style={{ fontSize: 10, color: 'var(--color-accent-primary)', fontFamily: 'var(--font-mono)' }}>
                score {hit._score.toFixed(2)}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
              {hit.snippet}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

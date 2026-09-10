/**
 * PipelineArtifactCards — Feature 2.
 *
 * Row of 4 clickable cards: Raw Logs, Anomaly Records, Incident Reports, Heal Report.
 * Each card shows: stage label, count (live / 30s refresh), last updated, status chip,
 * "View in OpenSearch" icon, "Refetch" icon.
 *
 * Clicking card body opens a 480px right-side drawer with paginated records,
 * search/filter bar, CSV export, and "Create Custom Dashboard" link.
 */

import { useState, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useArtifacts, useArtifactRecords } from '../hooks/useArtifacts';
import type { ArtifactCard } from '../designSystem';

const OS_DASHBOARDS_URL = import.meta.env.VITE_OPENSEARCH_DASHBOARDS_URL ?? 'http://localhost:5601';

const CARD_META: Record<ArtifactCard['key'], { stage: string; label: string }> = {
  'raw-logs':         { stage: 'Stage 1 — Ingestion',    label: 'Raw Logs' },
  'anomaly-records':  { stage: 'Stage 2 — Detection',    label: 'Anomaly Records' },
  'incident-reports': { stage: 'Stage 3 — Analysis',     label: 'Incident Reports' },
  'heal-report':      { stage: 'Stage 5 — Verification', label: 'Heal Report' },
};

function isLive(lastUpdated: string | null): boolean {
  if (!lastUpdated) return false;
  return Date.now() - new Date(lastUpdated).getTime() < 5 * 60 * 1000;
}

function formatLastUpdated(ts: string | null): string {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return ts; }
}

/** Export current page records as CSV client-side. */
function exportCsv(rows: Record<string, unknown>[], filename: string) {
  if (rows.length === 0) return;
  const keys = Object.keys(rows[0]);
  const csv = [
    keys.join(','),
    ...rows.map(r => keys.map(k => JSON.stringify(r[k] ?? '')).join(',')),
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function ArtifactDrawer({
  card, onClose,
}: {
  card: ArtifactCard;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const { data, loading, refetch } = useArtifactRecords(card.key, page, keyword);
  const meta = CARD_META[card.key];
  const totalPages = Math.ceil(data.total / 50) || 1;

  const openCustomDashboard = () => {
    window.open(
      `${OS_DASHBOARDS_URL}/app/dashboards#/create?indexPattern=${card.index}`,
      '_blank', 'noopener'
    );
  };

  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 700 }}
        aria-hidden="true"
      />

      {/* Drawer */}
      <motion.aside
        initial={{ x: 520 }} animate={{ x: 0 }} exit={{ x: 520 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, zIndex: 800,
          background: 'var(--color-bg-primary)',
          borderLeft: '1px solid var(--color-border-default)',
          display: 'flex', flexDirection: 'column',
          boxShadow: '-4px 0 32px rgba(0,0,0,0.25)',
        }}
        role="dialog"
        aria-label={`${meta.label} records`}
        aria-modal="true"
      >
        {/* Header */}
        <div style={{
          padding: 'var(--space-4) var(--space-5)',
          borderBottom: '1px solid var(--color-border-subtle)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-md)', color: 'var(--color-text-primary)' }}>{meta.label}</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>{meta.stage} · {card.index}</div>
          </div>
          <button id="artifact-drawer-close" onClick={onClose} className="btn-icon" aria-label="Close drawer">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <line x1="2" y1="2" x2="14" y2="14" /><line x1="14" y1="2" x2="2" y2="14" />
            </svg>
          </button>
        </div>

        {/* Toolbar */}
        <div style={{ padding: 'var(--space-3) var(--space-5)', borderBottom: '1px solid var(--color-border-subtle)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexShrink: 0 }}>
          <input
            id="artifact-drawer-search"
            type="search"
            placeholder="Filter records…"
            value={keyword}
            onChange={e => { setKeyword(e.target.value); setPage(1); }}
            aria-label="Filter records"
            style={{
              flex: 1, padding: '5px 10px',
              background: 'var(--color-bg-sunken)',
              border: '1px solid var(--color-border-subtle)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--color-text-primary)',
              fontSize: 'var(--text-xs)', outline: 'none',
            }}
          />
          <button
            id="artifact-drawer-csv"
            onClick={() => exportCsv(data.hits, `${card.key}-page${page}.csv`)}
            className="btn-ghost"
            aria-label="Export as CSV"
            style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M8 1v10M4 7l4 4 4-4" /><path d="M2 14h12" />
            </svg>
            CSV
          </button>
          <button
            id="artifact-drawer-dashboard"
            onClick={openCustomDashboard}
            className="btn-ghost"
            aria-label="Create custom OpenSearch dashboard"
            style={{ fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <rect x="1" y="1" width="6" height="6" rx="1" /><rect x="9" y="1" width="6" height="6" rx="1" />
              <rect x="1" y="9" width="6" height="6" rx="1" /><rect x="9" y="9" width="6" height="6" rx="1" />
            </svg>
            Dashboard
          </button>
          <button id="artifact-drawer-refetch" onClick={refetch} className="btn-icon" aria-label="Refresh records">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
              <path d="M1.5 8a6.5 6.5 0 0 1 12-3" /><path d="M14.5 8a6.5 6.5 0 0 1-12 3" />
              <polyline points="1.5,3 1.5,7 5,6" /><polyline points="14.5,13 14.5,9 11,10" />
            </svg>
          </button>
        </div>

        {/* Records */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>Loading…</div>
          ) : data.hits.length === 0 ? (
            <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>No records found.</div>
          ) : (
            data.hits.map((row, i) => (
              <div key={i} className="row-interactive" style={{
                padding: 'var(--space-2) var(--space-5)',
                borderBottom: '1px solid var(--color-border-subtle)',
                fontSize: 'var(--text-xs)',
              }}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  {JSON.stringify(row, null, 2)}
                </pre>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        <div style={{ padding: 'var(--space-3) var(--space-5)', borderTop: '1px solid var(--color-border-subtle)', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-3)', flexShrink: 0 }}>
          <button id="artifact-prev" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="btn-ghost" aria-label="Previous page" style={{ fontSize: 'var(--text-xs)' }}>← Prev</button>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Page {page} / {totalPages} ({data.total} total)</span>
          <button id="artifact-next" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="btn-ghost" aria-label="Next page" style={{ fontSize: 'var(--text-xs)' }}>Next →</button>
        </div>
      </motion.aside>
    </>
  );
}

export default function PipelineArtifactCards() {
  const { cards, loading, refetch } = useArtifacts();
  const [openCard, setOpenCard] = useState<ArtifactCard | null>(null);

  const openOsUrl = useCallback((card: ArtifactCard, e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(`${OS_DASHBOARDS_URL}/app/discover#/?_a=(index:${card.index})`, '_blank', 'noopener');
  }, []);

  const refetchCard = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    refetch();
  }, [refetch]);

  return (
    <>
      <div data-aos="fade-up" style={{ marginBottom: 'var(--space-6)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-md)', color: 'var(--color-text-primary)' }}>
            Pipeline Artifacts
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
          {loading
            ? Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass" style={{ borderRadius: 'var(--radius-lg)', height: 100, opacity: 0.5 }} />
              ))
            : cards.map(card => {
                const meta = CARD_META[card.key];
                const live = isLive(card.last_updated);
                return (
                  <button
                    key={card.key}
                    id={`artifact-card-${card.key}`}
                    onClick={() => setOpenCard(card)}
                    className="glass"
                    aria-label={`View ${meta.label} records`}
                    style={{
                      borderRadius: 'var(--radius-lg)',
                      padding: 'var(--space-4)',
                      border: '1px solid var(--color-border-subtle)',
                      cursor: 'pointer', textAlign: 'left',
                      transition: 'border-color 200ms, box-shadow 200ms',
                      position: 'relative',
                    }}
                    onFocus={e => { (e.currentTarget as HTMLElement).style.boxShadow = '0 0 0 2px var(--color-accent-primary)'; }}
                    onBlur={e => { (e.currentTarget as HTMLElement).style.boxShadow = 'none'; }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-accent-primary)'; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border-subtle)'; }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-2)' }}>
                      <span style={{ fontSize: 9, color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase' }}>
                        {meta.stage}
                      </span>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button
                          id={`artifact-os-${card.key}`}
                          onClick={e => openOsUrl(card, e)}
                          className="btn-icon"
                          aria-label={`Open ${meta.label} in OpenSearch`}
                          style={{ width: 20, height: 20, padding: 0 }}
                        >
                          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                            <path d="M6 3H3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-3" />
                            <path d="M10 1h5v5" /><path d="M15 1 8 8" />
                          </svg>
                        </button>
                        <button
                          id={`artifact-refetch-${card.key}`}
                          onClick={refetchCard}
                          className="btn-icon"
                          aria-label={`Refetch ${meta.label} count`}
                          style={{ width: 20, height: 20, padding: 0 }}
                        >
                          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
                            <path d="M1.5 8a6.5 6.5 0 0 1 12-3" /><path d="M14.5 8a6.5 6.5 0 0 1-12 3" />
                            <polyline points="1.5,3 1.5,7 5,6" /><polyline points="14.5,13 14.5,9 11,10" />
                          </svg>
                        </button>
                      </div>
                    </div>

                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', marginBottom: 4 }}>
                      {meta.label}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, color: 'var(--color-text-primary)', fontWeight: 700, marginBottom: 4 }}>
                      {card.count.toLocaleString()}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>
                        {formatLastUpdated(card.last_updated)}
                      </span>
                      <span style={{
                        fontSize: 9, padding: '2px 6px', borderRadius: 'var(--radius-full)', fontWeight: 600,
                        background: live ? 'rgba(45,122,79,0.1)' : 'rgba(202,138,4,0.1)',
                        color: live ? 'var(--color-status-success)' : 'var(--color-status-warning)',
                        border: `1px solid ${live ? 'rgba(45,122,79,0.2)' : 'rgba(202,138,4,0.2)'}`,
                      }}>
                        {live ? 'Live' : 'Stale'}
                      </span>
                    </div>
                  </button>
                );
              })}
        </div>
      </div>

      <AnimatePresence>
        {openCard && <ArtifactDrawer card={openCard} onClose={() => setOpenCard(null)} />}
      </AnimatePresence>
    </>
  );
}

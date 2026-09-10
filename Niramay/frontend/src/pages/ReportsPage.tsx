/**
 * ReportsPage — Feature 3: Report Generation Portal.
 *
 * Route: /reports
 *
 * Left half: generation form (report type, date range, severity multi-select, format).
 * Right half: report history table (auto-polls pending reports every 10s).
 * Ready reports have a "Download" button.
 * Navigation bar matches HealingDashboard's top-nav style.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useReports } from '../hooks/useReports';
import type { GenerateReportPayload } from '../hooks/useReports';
import type { Report } from '../designSystem';
import { timeAgo } from '../designSystem';
import { useToast } from '../components/ToastNotification';
import { useTheme } from '../designSystem';

const REPORT_TYPES = [
  { value: 'incident_summary', label: 'Incident Summary' },
  { value: 'heal_summary',     label: 'Heal Summary' },
  { value: 'full_pipeline',    label: 'Full Pipeline Report' },
];

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low'];
const FORMAT_OPTIONS = [
  { value: 'json', label: 'JSON' },
  { value: 'csv',  label: 'CSV' },
];

function StatusBadge({ status }: { status: Report['status'] }) {
  const map: Record<Report['status'], { cls: string; label: string }> = {
    pending: { cls: 'badge-warning', label: '⏳ Pending' },
    ready:   { cls: 'badge-success', label: '✓ Ready' },
    failed:  { cls: 'badge-error',   label: '✕ Failed' },
  };
  const { cls, label } = map[status] ?? { cls: 'badge-neutral', label: status };
  return <span className={`badge ${cls}`}>{label}</span>;
}

export default function ReportsPage() {
  const { addToast } = useToast();
  const { isDark, toggleTheme } = useTheme();
  const { reports, generating, generateError, generate, download } = useReports();

  const [form, setForm] = useState<GenerateReportPayload>({
    report_type: 'incident_summary',
    date_from: new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 16),
    date_to: new Date().toISOString().slice(0, 16),
    severities: [],
    format: 'json',
  });

  const toggleSeverity = (sev: string) => {
    setForm(f => ({
      ...f,
      severities: f.severities.includes(sev)
        ? f.severities.filter(s => s !== sev)
        : [...f.severities, sev],
    }));
  };

  const handleGenerate = async () => {
    const ok = await generate(form);
    if (ok) addToast('Report generation started', 'info');
    else addToast(generateError ?? 'Failed to generate report', 'error');
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg-primary)', color: 'var(--color-text-primary)' }}>
      {/* Top nav */}
      <nav style={{
        height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 var(--space-8)',
        borderBottom: '1px solid var(--color-border-subtle)',
        background: 'var(--color-bg-secondary)',
        position: 'sticky', top: 0, zIndex: 200,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-md)', color: 'var(--color-text-primary)', letterSpacing: 'var(--tracking-wider)' }}>
            NIRAMAY
          </span>
          <span style={{ color: 'var(--color-border-subtle)', fontSize: 14 }}>/</span>
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-accent-primary)', fontWeight: 600 }}>Reports</span>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-sm)', alignItems: 'center' }}>
          <Link to="/dashboard" style={{ color: 'var(--color-text-secondary)', textDecoration: 'none' }}>Dashboard</Link>
          <Link to="/visualizer" style={{ color: 'var(--color-text-secondary)', textDecoration: 'none' }}>Visualizer</Link>
          <Link to="/reports" style={{ color: 'var(--color-accent-primary)', textDecoration: 'none', fontWeight: 600 }}>Reports</Link>
          <div style={{ borderLeft: '1px solid var(--color-border-subtle)', paddingLeft: 'var(--space-4)', marginLeft: 'var(--space-2)' }}>
            <button
              onClick={toggleTheme}
              className="btn-icon"
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
                  <circle cx="8" cy="8" r="3.5" />
                  <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.05 3.05l1.06 1.06M11.89 11.89l1.06 1.06M3.05 12.95l1.06-1.06M11.89 4.11l1.06-1.06" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
                  <path d="M13.5 8.5a5.5 5.5 0 0 1-6-6A5.5 5.5 0 1 0 13.5 8.5Z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: 'var(--space-8)', display: 'grid', gridTemplateColumns: '360px 1fr', gap: 'var(--space-8)' }}>

        {/* Left — Generation form */}
        <div>
          <h1 style={{ fontSize: 'var(--text-xl)', fontFamily: 'var(--font-display)', marginBottom: 'var(--space-2)' }}>
            Generate Report
          </h1>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-tertiary)', marginBottom: 'var(--space-6)', lineHeight: 'var(--leading-loose)' }}>
            Query OpenSearch indices and export incident, healing, or full pipeline data.
          </p>

          <div className="glass card-glass" style={{ padding: 'var(--space-6)', borderRadius: 'var(--radius-xl)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>

              {/* Report type */}
              <div>
                <label htmlFor="report-type-select" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  Report Type
                </label>
                <select
                  id="report-type-select"
                  value={form.report_type}
                  onChange={e => setForm(f => ({ ...f, report_type: e.target.value as GenerateReportPayload['report_type'] }))}
                  style={{
                    width: '100%', padding: '8px 12px',
                    background: 'var(--color-bg-sunken)',
                    border: '1px solid var(--color-border-default)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--color-text-primary)',
                    fontSize: 'var(--text-sm)',
                  }}
                >
                  {REPORT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>

              {/* Date from */}
              <div>
                <label htmlFor="report-date-from" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  From
                </label>
                <input
                  type="datetime-local"
                  id="report-date-from"
                  value={form.date_from}
                  onChange={e => setForm(f => ({ ...f, date_from: e.target.value }))}
                  style={{
                    width: '100%', padding: '8px 12px',
                    background: 'var(--color-bg-sunken)',
                    border: '1px solid var(--color-border-default)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--color-text-primary)',
                    fontSize: 'var(--text-sm)',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Date to */}
              <div>
                <label htmlFor="report-date-to" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  To
                </label>
                <input
                  type="datetime-local"
                  id="report-date-to"
                  value={form.date_to}
                  onChange={e => setForm(f => ({ ...f, date_to: e.target.value }))}
                  style={{
                    width: '100%', padding: '8px 12px',
                    background: 'var(--color-bg-sunken)',
                    border: '1px solid var(--color-border-default)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--color-text-primary)',
                    fontSize: 'var(--text-sm)',
                    boxSizing: 'border-box',
                  }}
                />
              </div>

              {/* Severities */}
              <div>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  Severities (all if none selected)
                </span>
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {SEVERITY_OPTIONS.map(sev => (
                    <button
                      key={sev}
                      id={`report-sev-${sev}`}
                      onClick={() => toggleSeverity(sev)}
                      aria-pressed={form.severities.includes(sev)}
                      style={{
                        padding: '4px 10px', borderRadius: 'var(--radius-full)',
                        fontSize: 'var(--text-xs)', fontWeight: 600,
                        cursor: 'pointer', textTransform: 'capitalize',
                        background: form.severities.includes(sev) ? 'var(--color-accent-primary)' : 'var(--color-bg-sunken)',
                        color: form.severities.includes(sev) ? 'var(--color-text-inverse)' : 'var(--color-text-secondary)',
                        border: `1px solid ${form.severities.includes(sev) ? 'var(--color-accent-primary)' : 'var(--color-border-subtle)'}`,
                        transition: 'all 150ms',
                      }}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>

              {/* Format */}
              <div>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', letterSpacing: 'var(--tracking-wider)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  Format
                </span>
                <div style={{ display: 'flex', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-sunken)', border: '1px solid var(--color-border-subtle)', overflow: 'hidden', width: 'fit-content' }}>
                  {FORMAT_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      id={`report-format-${opt.value}`}
                      onClick={() => setForm(f => ({ ...f, format: opt.value as 'json' | 'csv' }))}
                      aria-pressed={form.format === opt.value}
                      style={{
                        padding: '5px 16px',
                        background: form.format === opt.value ? 'var(--color-accent-primary)' : 'transparent',
                        color: form.format === opt.value ? 'var(--color-text-inverse)' : 'var(--color-text-secondary)',
                        border: 'none', fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
                        transition: 'all 150ms',
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Generate button */}
              <button
                id="report-generate-btn"
                onClick={handleGenerate}
                disabled={generating}
                aria-busy={generating}
                style={{
                  width: '100%', padding: '10px',
                  background: generating ? 'var(--color-bg-sunken)' : 'var(--color-accent-primary)',
                  color: generating ? 'var(--color-text-tertiary)' : 'var(--color-text-inverse)',
                  border: 'none', borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--text-sm)', fontWeight: 700,
                  cursor: generating ? 'wait' : 'pointer',
                  transition: 'all 150ms',
                  marginTop: 'var(--space-2)',
                }}
              >
                {generating ? 'Generating…' : 'Generate Report'}
              </button>

              {generateError && (
                <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--color-status-error)' }}>{generateError}</p>
              )}
            </div>
          </div>
        </div>

        {/* Right — Report history */}
        <div>
          <h2 style={{ fontSize: 'var(--text-xl)', fontFamily: 'var(--font-display)', marginBottom: 'var(--space-2)' }}>
            Report History
          </h2>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-tertiary)', marginBottom: 'var(--space-6)', lineHeight: 'var(--leading-loose)' }}>
            Pending reports auto-poll every 10 seconds. Ready reports can be downloaded.
          </p>

          {reports.length === 0 ? (
            <div className="glass card-glass" style={{ padding: 'var(--space-16)', textAlign: 'center', borderRadius: 'var(--radius-xl)' }}>
              <p style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>
                No reports generated yet.
              </p>
            </div>
          ) : (
            <div className="glass card-glass" style={{ borderRadius: 'var(--radius-xl)', overflow: 'hidden' }}>
              {/* Table header */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 120px 100px 80px 80px',
                gap: 'var(--space-3)',
                padding: 'var(--space-3) var(--space-5)',
                borderBottom: '1px solid var(--color-border-subtle)',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-tertiary)',
                letterSpacing: 'var(--tracking-wider)',
                textTransform: 'uppercase',
              }}>
                <span>Type</span>
                <span>Status</span>
                <span>Rows</span>
                <span>Format</span>
                <span>Actions</span>
              </div>

              {/* Rows */}
              {reports.map(report => (
                <div
                  key={report.report_id}
                  className="row-interactive"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 120px 100px 80px 80px',
                    gap: 'var(--space-3)',
                    padding: 'var(--space-3) var(--space-5)',
                    borderBottom: '1px solid var(--color-border-subtle)',
                    fontSize: 'var(--text-xs)',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ color: 'var(--color-text-primary)', fontWeight: 600, textTransform: 'capitalize', marginBottom: 2 }}>
                      {report.report_type.replace(/_/g, ' ')}
                    </div>
                    <div style={{ color: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                      {report.created_at ? timeAgo(report.created_at) : ''}
                    </div>
                  </div>
                  <StatusBadge status={report.status} />
                  <span style={{ color: 'var(--color-text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    {report.row_count !== null ? report.row_count.toLocaleString() : '—'}
                  </span>
                  <span style={{ color: 'var(--color-text-secondary)', textTransform: 'uppercase', fontWeight: 600 }}>
                    {report.format}
                  </span>
                  <div>
                    {report.status === 'ready' && (
                      <button
                        id={`report-download-${report.report_id.slice(0, 8)}`}
                        onClick={() => download(report.report_id)}
                        className="btn-ghost"
                        aria-label={`Download report ${report.report_id.slice(0, 8)}`}
                        style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 4 }}
                      >
                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                          <path d="M8 1v10M4 7l4 4 4-4" /><path d="M2 14h12" />
                        </svg>
                        DL
                      </button>
                    )}
                    {report.status === 'pending' && (
                      <div style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid var(--color-status-warning)', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

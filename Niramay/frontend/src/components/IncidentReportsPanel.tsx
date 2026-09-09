import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { IncidentReport, timeAgo } from '../designSystem';

interface IncidentReportsPanelProps {
  reports: IncidentReport[];
}

export const IncidentReportsPanel: React.FC<IncidentReportsPanelProps> = ({ reports }) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!reports || reports.length === 0) {
    return (
      <div className="glass card-glass" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-8)' }}>
        <p style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>No incident reports available</p>
      </div>
    );
  }

  const getSeverityColor = (sev: string) => {
    switch (sev) {
      case 'critical':
      case 'high':   return 'var(--color-status-error)';
      case 'medium': return 'var(--color-status-warning)';
      default:       return 'var(--color-accent-primary)';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
      case 'SUCCESS':
      case 'HEALED':          return 'var(--color-status-success)';
      case 'PENDING':
      case 'FAILED_RETRYING': return 'var(--color-status-warning)';
      case 'ESCALATED':
      case 'FAILURE':         return 'var(--color-status-error)';
      default:                return 'var(--color-text-tertiary)';
    }
  };

  return (
    <div className="glass card-glass" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-5) var(--space-6) var(--space-3)',
        borderBottom: '1px solid var(--color-border-subtle)',
        flexShrink: 0,
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-md)',
          color: 'var(--color-text-primary)',
        }}>
          Incident Reports
        </span>
        <span className="badge badge-error">{reports.length} Reports</span>
      </div>

      {/* Report list */}
      <div className="scroll-fade" style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--space-3) var(--space-6) var(--space-6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
      }}>
        {reports.map((report) => (
          <div
            key={report.detection_id}
            className="row-interactive"
            style={{ flexDirection: 'column', alignItems: 'stretch', borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-2)' }}
          >
            {/* Collapsed row header */}
            <div
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
              onClick={() => setExpandedId(expandedId === report.detection_id ? null : report.detection_id)}
            >
              <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
                <span className={`badge badge-${report.severity === 'critical' || report.severity === 'high' ? 'error' : 'warning'}`}>
                  {report.severity.toUpperCase()}
                </span>
                <span style={{
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  fontSize: 'var(--text-sm)',
                  color: 'var(--color-text-primary)',
                }}>
                  {report.service}
                </span>
                <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>
                  {timeAgo(report.timestamp)}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                <span style={{
                  fontSize: 11,
                  padding: '2px 6px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: `${getStatusColor(report.verification_status)}22`,
                  color: getStatusColor(report.verification_status),
                  border: `1px solid ${getStatusColor(report.verification_status)}55`,
                }}>
                  {report.verification_status}
                </span>
                <span style={{ color: 'var(--color-text-tertiary)', fontSize: 18 }}>
                  {expandedId === report.detection_id ? '▼' : '▶'}
                </span>
              </div>
            </div>

            {/* Expanded markdown content */}
            {expandedId === report.detection_id && (
              <div style={{
                marginTop: 'var(--space-3)',
                background: 'var(--color-bg-sunken)',
                padding: 'var(--space-4)',
                borderRadius: 'var(--radius-md)',
                fontSize: 'var(--text-sm)',
                lineHeight: 'var(--leading-loose)',
                color: 'var(--color-text-secondary)',
                borderTop: '1px solid var(--color-border-subtle)',
              }}>
                <ReactMarkdown
                  components={{
                    h2: ({ node, ...props }) => (
                      <h3 style={{
                        marginTop: 'var(--space-4)',
                        marginBottom: 'var(--space-2)',
                        color: 'var(--color-text-primary)',
                        borderBottom: '1px solid var(--color-border-subtle)',
                        paddingBottom: 'var(--space-1)',
                        fontSize: 'var(--text-sm)',
                      }} {...props} />
                    ),
                    table: ({ node, ...props }) => (
                      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 'var(--space-4)' }} {...props} />
                    ),
                    th: ({ node, ...props }) => (
                      <th style={{
                        textAlign: 'left',
                        padding: 'var(--space-1) var(--space-2)',
                        borderBottom: '1px solid var(--color-border-subtle)',
                        color: 'var(--color-text-tertiary)',
                        fontSize: 'var(--text-xs)',
                      }} {...props} />
                    ),
                    td: ({ node, ...props }) => (
                      <td style={{
                        padding: 'var(--space-1) var(--space-2)',
                        borderBottom: '1px solid var(--color-border-subtle)',
                      }} {...props} />
                    ),
                    blockquote: ({ node, ...props }) => (
                      <blockquote style={{
                        borderLeft: '3px solid var(--color-status-warning)',
                        margin: 'var(--space-4) 0',
                        paddingLeft: 'var(--space-3)',
                        color: 'var(--color-text-tertiary)',
                      }} {...props} />
                    ),
                  }}
                >
                  {report.human_report}
                </ReactMarkdown>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

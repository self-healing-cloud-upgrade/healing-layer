/**
 * DetectionAlerts — Anomaly detection panel with Chart.js bar chart.
 * Glass panel. Rounded bars. Severity dots. Reason tags on hover.
 * All data contracts preserved.
 */

import { useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Chart, registerables } from 'chart.js';
import { timeAgo, useTheme, type AnomalyLog, type SystemStats } from '../designSystem';
import EmptyState from './EmptyState';
import { SkeletonRow, SkeletonChart } from './SkeletonBlock';

Chart.register(...registerables);

function severityDot(severity: string): string {
  if (severity === 'critical' || severity === 'high') return 'error';
  if (severity === 'medium') return 'warning';
  return 'neutral';
}

export default function DetectionAlerts({ 
  anomalies, 
  stats 
}: { 
  anomalies: AnomalyLog[];
  stats: SystemStats | null;
}) {
  const { isDark } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);
  const seenIdsRef = useRef<Set<string>>(new Set());

  const chartData = useMemo(
    () => stats?.by_type
      ? Object.entries(stats.by_type).map(([name, count]) => ({
          name: name.replace(/_/g, ' '),
          count,
        }))
      : [],
    [stats]
  );

  // Chart.js bar chart
  useEffect(() => {
    if (!canvasRef.current || chartData.length === 0) return;

    const baseColor = isDark ? 'rgba(212, 132, 94, 0.6)' : 'rgba(196, 101, 58, 0.5)';
    const colors = chartData.map((_, i) => {
      const opacity = 0.3 + (i * 0.2);
      return isDark
        ? `rgba(212, 132, 94, ${Math.min(opacity, 0.8)})`
        : `rgba(196, 101, 58, ${Math.min(opacity, 0.7)})`;
    });

    if (chartRef.current) {
      chartRef.current.data.labels = chartData.map(d => d.name);
      chartRef.current.data.datasets[0].data = chartData.map(d => d.count);
      chartRef.current.data.datasets[0].backgroundColor = colors;
      chartRef.current.update('none');
      return;
    }

    chartRef.current = new Chart(canvasRef.current, {
      type: 'bar',
      data: {
        labels: chartData.map(d => d.name),
        datasets: [{
          data: chartData.map(d => d.count),
          backgroundColor: colors,
          borderColor: 'transparent',
          borderRadius: 8,
          borderSkipped: false,
          barPercentage: 0.6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 900, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: isDark ? 'rgba(30, 27, 23, 0.9)' : 'rgba(255, 255, 255, 0.9)',
            titleColor: isDark ? '#F0EBE3' : '#1C1812',
            bodyColor: isDark ? 'rgba(240, 235, 227, 0.7)' : 'rgba(28, 24, 18, 0.7)',
            borderColor: isDark ? 'rgba(255, 248, 235, 0.1)' : 'rgba(28, 24, 18, 0.1)',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 8,
            titleFont: { family: 'DM Sans', size: 11 },
            bodyFont: { family: 'DM Sans', size: 11 },
          },
        },
        scales: {
          x: {
            border: { display: false },
            grid: { display: false },
            ticks: {
              color: isDark ? 'rgba(240, 235, 227, 0.3)' : 'rgba(28, 24, 18, 0.3)',
              font: { family: 'DM Sans', size: 9 },
            },
          },
          y: { display: false },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [chartData, isDark]);

  return (
    <div
      id="detection-alerts"
      className="glass card-glass"
      style={{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-5) var(--space-6) var(--space-3)',
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-md)',
          color: 'var(--color-text-primary)',
        }}>
          Detection
        </span>
        {stats && stats.total_anomalies > 0 && (
          <span className="badge badge-warning">{stats.total_anomalies} anomalies</span>
        )}
      </div>

      {/* Bar chart */}
      {chartData.length > 0 ? (
        <div style={{ padding: '0 var(--space-6)', height: 72, opacity: 0.8 }}>
          <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
        </div>
      ) : stats === null ? (
        <SkeletonChart />
      ) : null}

      {/* Anomaly rows */}
      <div className="scroll-fade" style={{
        flex: 1,
        padding: 'var(--space-3) var(--space-6) var(--space-6)',
        maxHeight: 360,
        overflowY: 'auto',
      }}>
        {stats === null ? (
          <div>
            <SkeletonRow /><SkeletonRow /><SkeletonRow />
          </div>
        ) : anomalies.length === 0 ? (
          <EmptyState headline="No anomalies detected" />
        ) : (
          <AnimatePresence initial={false}>
            {(anomalies || []).map((a, i) => {
              if (!a) return null;
              const aKey = a.detection_id || `${a.timestamp}-${i}`;
              const isNew = !seenIdsRef.current.has(aKey);
              if (isNew) seenIdsRef.current.add(aKey);
              if (seenIdsRef.current.size > 200) {
                const arr = Array.from(seenIdsRef.current);
                seenIdsRef.current = new Set(arr.slice(-100));
              }
              return (
                <motion.div
                  key={aKey}
                initial={isNew ? { opacity: 0, y: 12 } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={isNew ? {
                  duration: 0.3,
                  delay: Math.min(i * 0.04, 0.4),
                  ease: [0.16, 1, 0.3, 1],
                } : { duration: 0 }}
                className="row-interactive"
                style={{
                  padding: 'var(--space-3) var(--space-2)',
                  marginBottom: 2,
                  cursor: 'default',
                }}
              >
                {/* Top row: severity + score + method + time */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  marginBottom: 'var(--space-1)',
                }}>
                  <span className={`dot dot-${severityDot(a.severity)}`} />

                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                    color: `var(--color-status-${severityDot(a.severity)})`,
                    fontVariantNumeric: 'tabular-nums',
                  }}>
                    {a.anomaly_score.toFixed(2)}
                  </span>

                  <span style={{
                    fontSize: 'var(--text-xs)',
                    fontWeight: 'var(--font-weight-medium)' as any,
                    letterSpacing: 'var(--tracking-wider)',
                    textTransform: 'uppercase',
                    color: 'var(--color-text-secondary)',
                    fontFamily: 'var(--font-mono)',
                  }}>
                    {a.method}
                  </span>

                  {a.failure_tag && a.failure_tag !== 'none' && (
                    <span className="badge badge-accent" style={{ fontSize: 8, padding: '0 5px', letterSpacing: '0.02em' }}>
                      {a.failure_tag.replace(/_/g, ' ')}
                    </span>
                  )}

                  {a.requires_llm && (
                    <span className="badge badge-accent" style={{ fontSize: 8, padding: '0 4px' }}>AI</span>
                  )}

                  <span style={{ flex: 1 }} />

                  <span className="subtle-on-hover" style={{
                    fontSize: 10,
                    color: 'var(--color-text-tertiary)',
                  }}>
                    {timeAgo(a.timestamp)}
                  </span>
                </div>

                {/* Endpoint */}
                <div style={{
                  fontSize: 'var(--text-sm)',
                  color: 'var(--color-text-primary)',
                  paddingLeft: 'var(--space-4)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {a.endpoint}
                </div>

                {/* Reason tags — progressive disclosure */}
                {a.anomaly_reasons.length > 0 && (
                  <div className="reveal-on-hover" style={{
                    display: 'flex',
                    gap: 'var(--space-1)',
                    flexWrap: 'wrap',
                    marginTop: 'var(--space-2)',
                    paddingLeft: 'var(--space-4)',
                  }}>
                    {a.anomaly_reasons.map((r, ri) => (
                      <span key={ri} className="badge badge-neutral" style={{
                        fontSize: 10,
                        padding: '1px 8px',
                      }}>
                        {r.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}

/**
 * ObservationFeed — Live API traffic log with Chart.js sparkline.
 * Glass panel. Row-based layout. Status dots. Progressive disclosure.
 * Skeleton loading state. All data contracts preserved.
 */

import { useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Chart, registerables } from 'chart.js';
import { timeAgo, statusDotClass, useTheme, type ObservationLog } from '../designSystem';
import EmptyState from './EmptyState';
import { SkeletonRow, SkeletonChart } from './SkeletonBlock';

Chart.register(...registerables);

export default function ObservationFeed({ logs }: { logs: ObservationLog[] }) {
  const { isDark } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  // Track which log IDs we've already rendered to avoid re-animating
  const seenIdsRef = useRef<Set<string>>(new Set());

  const sparkData = useMemo(
    () => logs.slice(0, 20).reverse().map(l => l.response_time_ms),
    [logs]
  );

  // Chart.js sparkline
  useEffect(() => {
    if (!canvasRef.current || sparkData.length < 3) return;

    const accentColor = isDark ? 'rgba(212, 132, 94, 0.7)' : 'rgba(196, 101, 58, 0.7)';
    const fillColor = isDark ? 'rgba(212, 132, 94, 0.08)' : 'rgba(196, 101, 58, 0.06)';

    if (chartRef.current) {
      chartRef.current.data.labels = sparkData.map((_, i) => i);
      chartRef.current.data.datasets[0].data = sparkData;
      chartRef.current.data.datasets[0].borderColor = accentColor;
      chartRef.current.data.datasets[0].backgroundColor = fillColor;
      chartRef.current.update('none');
      return;
    }

    chartRef.current = new Chart(canvasRef.current, {
      type: 'line',
      data: {
        labels: sparkData.map((_, i) => i),
        datasets: [{
          data: sparkData,
          borderColor: accentColor,
          backgroundColor: fillColor,
          fill: true,
          tension: 0.4,
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 3,
          pointHoverBackgroundColor: accentColor,
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
            callbacks: {
              title: () => '',
              label: (ctx) => `${(ctx.parsed.y ?? 0).toFixed(0)}ms`,
            },
          },
        },
        scales: {
          x: { display: false },
          y: { display: false },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [sparkData, isDark]);

  const statusColorVar = (code: number) => {
    const cls = statusDotClass(code);
    if (cls === 'neutral') return 'var(--color-text-tertiary)';
    return `var(--color-status-${cls})`;
  };

  return (
    <div
      id="observation-feed"
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-md)',
            color: 'var(--color-text-primary)',
          }}>
            Observation
          </span>
          <span className="dot dot-success dot-live" />
        </div>
        <span className="badge badge-neutral">
          {logs.length}
        </span>
      </div>

      {/* Sparkline */}
      {sparkData.length > 2 ? (
        <div style={{ padding: '0 var(--space-6)', height: 36, opacity: 0.7 }}>
          <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
        </div>
      ) : (
        <SkeletonChart />
      )}

      {/* Request rows */}
      <div className="scroll-fade" style={{
        flex: 1,
        padding: 'var(--space-2) var(--space-6) var(--space-6)',
        maxHeight: 380,
        overflowY: 'auto',
      }}>
        {logs.length === 0 ? <EmptyState headline="Waiting for traffic" /> : (
          <AnimatePresence initial={false}>
            {logs.map((log, i) => {
              const logKey = log.request_id || `${log.timestamp}-${i}`;
              const isNew = !seenIdsRef.current.has(logKey);
              if (isNew) seenIdsRef.current.add(logKey);
              // Keep set bounded
              if (seenIdsRef.current.size > 200) {
                const iter = seenIdsRef.current.values();
                for (let j = 0; j < 100; j++) iter.next();
                const keep = new Set<string>();
                for (const v of iter) keep.add(v);
                seenIdsRef.current = keep;
              }
              return (
              <motion.div
                key={logKey}
                initial={isNew ? { opacity: 0, y: 12 } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={isNew ? {
                  duration: 0.3,
                  delay: Math.min(i * 0.03, 0.3),
                  ease: [0.16, 1, 0.3, 1],
                } : { duration: 0 }}
                className="row-interactive"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-3)',
                  padding: 'var(--space-3) var(--space-2)',
                  cursor: 'default',
                }}
              >
                <span className={`dot dot-${statusDotClass(log.status_code)}`} />

                <span style={{
                  fontSize: 'var(--text-xs)',
                  fontWeight: 'var(--font-weight-medium)' as any,
                  letterSpacing: 'var(--tracking-wider)',
                  textTransform: 'uppercase',
                  color: 'var(--color-text-secondary)',
                  width: 36,
                  flexShrink: 0,
                  fontFamily: 'var(--font-mono)',
                }}>
                  {log.method}
                </span>

                <span style={{
                  flex: 1,
                  fontSize: 'var(--text-sm)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  color: 'var(--color-text-primary)',
                }} title={log.endpoint}>
                  {log.endpoint.replace('/api/v1/', '/')}
                </span>

                <span style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  color: statusColorVar(log.status_code),
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {log.status_code}
                </span>

                <span className="subtle-on-hover" style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  color: 'var(--color-text-tertiary)',
                  width: 48,
                  textAlign: 'right',
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {(log.response_time_ms ?? 0).toFixed(0)}ms
                </span>

                <span className="reveal-on-hover" style={{
                  fontSize: 10,
                  color: 'var(--color-text-tertiary)',
                  width: 32,
                  textAlign: 'right',
                }}>
                  {timeAgo(log.timestamp)}
                </span>
              </motion.div>
            )})}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}

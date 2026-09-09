/**
 * PipelineStageIndicator
 *
 * Horizontal step indicator showing the live pipeline progress.
 * Polls /api/v1/pipeline/stage every 2 seconds via usePipelineStage.
 *
 * Stages: Ingesting → Detecting → Analysing → Healing → Verifying → Complete
 *
 * Handles staleness: if the pipeline stage hasn't updated in >60s and
 * is not a terminal state, shows as idle/stale.
 */

import { usePipelineStage } from '../hooks/useNiramayData';

const STEPS = [
  { key: 'ingesting',  label: 'Ingesting',  stages: ['stage_1_complete'] },
  { key: 'detecting',  label: 'Detecting',  stages: ['stage_2_complete'] },
  { key: 'analysing',  label: 'Analysing',  stages: ['stage_3_causal_engine_running', 'stage_3_complete'] },
  { key: 'healing',    label: 'Healing',    stages: ['stage_4_healing_executing', 'stage_4_healing_complete'] },
  { key: 'verifying',  label: 'Verifying',  stages: [] },
  { key: 'complete',   label: 'Complete',   stages: ['healing_complete'] },
];

// Map a pipeline stage string → step index (0-based)
function stageToStepIndex(stage: string): number {
  if (!stage || stage === 'idle' || stage === 'unknown') return -1;
  if (stage === 'stage_1_complete') return 0;
  if (stage === 'stage_2_complete') return 1;
  if (stage === 'stage_3_causal_engine_running' || stage === 'stage_3_complete') return 2;
  if (stage === 'stage_4_healing_executing' || stage === 'stage_4_healing_complete') return 3;
  if (stage === 'healing_complete') return 5;
  if (stage === 'healing_failed_escalated') return 5;
  if (stage === 'healing_failed_email_sent') return 5;
  return -1;
}

function isPulsing(stage: string, stepIdx: number): boolean {
  const currentIdx = stageToStepIndex(stage);
  if (currentIdx !== stepIdx) return false;
  return stage === 'stage_3_causal_engine_running' || stage === 'stage_4_healing_executing';
}

function isEscalated(stage: string): boolean {
  return stage === 'healing_failed_escalated' || stage === 'healing_failed_email_sent';
}

function isEmailSent(stage: string): boolean {
  return stage === 'healing_failed_email_sent';
}

export default function PipelineStageIndicator() {
  const data = usePipelineStage(true);

  // Show idle state when nothing is happening
  if (!data || data.stage === 'idle' || data.stage === 'unknown') {
    return (
      <div
        style={{
          background: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-3) var(--space-6)',
          marginBottom: 'var(--space-8)',
          opacity: 0.7,
        }}
        role="status"
        aria-label="Pipeline idle"
      >
        <p style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-tertiary)',
          margin: 0,
          fontStyle: 'italic',
        }}>
          ⏸ Idle — waiting for logs. Start the consumer to begin monitoring.
        </p>
      </div>
    );
  }

  // If the data is stale (server marked it as >60s old non-terminal), show subtle idle
  if (data.stale) {
    return (
      <div
        style={{
          background: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-3) var(--space-6)',
          marginBottom: 'var(--space-8)',
          opacity: 0.6,
        }}
        role="status"
        aria-label="Pipeline idle"
      >
        <p style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-tertiary)',
          margin: 0,
          fontStyle: 'italic',
        }}>
          Pipeline idle — last activity: {data.message}
        </p>
      </div>
    );
  }

  const currentStepIdx = stageToStepIndex(data.stage);
  const escalated = isEscalated(data.stage);
  const isComplete = data.stage === 'healing_complete';

  return (
    <div
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-5) var(--space-6)',
        marginBottom: 'var(--space-8)',
      }}
      role="status"
      aria-label="Pipeline stage progress"
      aria-live="polite"
    >
      {/* Step track */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 0,
        marginBottom: 'var(--space-4)',
      }}>
        {STEPS.map((step, idx) => {
          const isDone = currentStepIdx > idx;
          const isActive = currentStepIdx === idx;
          const pulsing = isPulsing(data.stage, idx);

          // Colour logic
          let dotColor = 'var(--color-border-default)'; // future
          if (escalated && idx === 5) dotColor = 'var(--color-status-error, #e05252)';
          else if (isComplete) dotColor = 'var(--color-status-success)';
          else if (isDone) dotColor = 'var(--color-status-success)';
          else if (isActive) dotColor = escalated ? 'var(--color-status-error, #e05252)' : 'var(--color-accent-primary)';

          let labelColor = 'var(--color-text-tertiary)';
          if (isActive || isDone) labelColor = 'var(--color-text-primary)';

          return (
            <div key={step.key} style={{ display: 'flex', alignItems: 'center', flex: idx < STEPS.length - 1 ? 1 : undefined }}>
              {/* Dot */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    background: dotColor,
                    flexShrink: 0,
                    transition: 'background 300ms',
                    animation: pulsing ? 'pulse 1.4s ease-in-out infinite' : undefined,
                  }}
                />
                <span style={{
                  fontSize: 10,
                  color: labelColor,
                  whiteSpace: 'nowrap',
                  fontWeight: isActive ? 600 : 400,
                  letterSpacing: 'var(--tracking-wider)',
                  textTransform: 'uppercase',
                  transition: 'color 300ms',
                }}>
                  {step.label}
                </span>
              </div>
              {/* Connector line */}
              {idx < STEPS.length - 1 && (
                <div style={{
                  flex: 1,
                  height: 1,
                  background: isDone ? 'var(--color-status-success)' : 'var(--color-border-subtle)',
                  marginBottom: 14,
                  transition: 'background 300ms',
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* Subtitle message */}
      <p style={{
        fontSize: 'var(--text-sm)',
        color: escalated
          ? 'var(--color-status-error, #e05252)'
          : isComplete
          ? 'var(--color-status-success)'
          : 'var(--color-text-secondary)',
        margin: 0,
        lineHeight: 'var(--leading-normal)',
      }}>
        {/* Context line */}
        {data.service && data.failure_tag && data.failure_tag !== 'none' && (
          <span style={{ fontWeight: 500 }}>
            {data.failure_tag} detected in {data.service} — initiating healing
            {' · '}
          </span>
        )}
        {data.message}
        {isComplete && data.time_to_heal !== undefined && data.time_to_heal !== null && (
          <span style={{ marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
            · healed in {Number(data.time_to_heal).toFixed(1)}s
          </span>
        )}
        {isEmailSent(data.stage) && (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            marginLeft: 8,
            padding: '2px 8px',
            background: 'rgba(220, 38, 38, 0.1)',
            borderRadius: 4,
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--color-status-error, #e05252)',
          }}>
            ✉️ Developer notified via email
          </span>
        )}
      </p>

      {/* Inline keyframe for pulsing */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.3); }
        }
      `}</style>
    </div>
  );
}

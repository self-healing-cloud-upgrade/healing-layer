/**
 * usePipelineEvents — Polls /api/v1/pipeline/events every 2s.
 * Returns the last N pipeline stage transition events and the current active stage label.
 * Used by PipelineProgressBar (Feature 4).
 *
 * Also fires toast notifications on stage transitions (Feature 3).
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { PipelineEvent } from '../designSystem';
import { useToast } from '../components/ToastNotification';

// Module-level singletons so multiple mounted instances (dashboard + visualizer
// pre-rendered side-by-side) never fire the same toast twice.
let _lastToastedStage: string | null = null;
let _firstHealShown = false;

const STAGE_LABELS: Record<string, string> = {
  stage_1_complete: 'Ingestion',
  stage_2_complete: 'Detection',
  stage_3_causal_engine_running: 'Analysis',
  stage_3_complete: 'Analysis',
  stage_4_healing_executing: 'Healing',
  stage_4_healing_complete: 'Healing',
  stage_5_cooldown: 'Cooldown',
  stage_6_verification_running: 'Verification',
  healing_complete: 'Complete',
  healing_failed_escalated: 'Failed',
  healing_failed_email_sent: 'Failed',
  stage_4_awaiting_approval: 'Healing',
};

/**
 * Direct stage → toast message mapping.
 *
 * Each new pipeline stage produces exactly ONE toast.
 * The message describes what is happening NOW (not what
 * completed), so it always matches the pipeline progress bar.
 */
const STAGE_TOAST_MESSAGES: Record<string, { message: string; kind: 'success' | 'error' | 'info' | 'warning' }> = {
  stage_1_complete:              { message: 'Ingestion Complete — Detection has started',                               kind: 'info'    },
  stage_2_complete:              { message: 'Detection Complete — Anomalies found, analysis starting',                  kind: 'info'    },
  stage_3_causal_engine_running: { message: 'AI Causal Analysis in progress',                                           kind: 'info'    },
  stage_3_complete:              { message: 'Analysis Complete — Healing action starting',                              kind: 'info'    },
  stage_4_healing_executing:     { message: '🔧 Healing in progress — Autonomous remediation executing',                kind: 'info'    },
  stage_5_cooldown:              { message: 'Healing action completed — Cooldown period active',                        kind: 'info'    },
  stage_6_verification_running:  { message: 'Verification in progress — Checking if anomaly is resolved',              kind: 'info'    },
  healing_complete:              { message: '✅ Healing & Verification Complete — System is healthy and ready to use',   kind: 'success' },
  healing_failed_escalated:      { message: '⚠️ Healing Failed — Escalated for manual review',                          kind: 'error'   },
  healing_failed_email_sent:     { message: '⚠️ Healing Failed — Developer notified via email',                         kind: 'error'   },
  stage_4_awaiting_approval:     { message: 'Healing queued — Awaiting manual approval',                                kind: 'warning' },
};

export type NodeState = 'idle' | 'active' | 'completed' | 'failed';

export interface PipelineNodeStatus {
  label: string;
  state: NodeState;
  timestamp?: string;
}

/** Maps the current pipeline stage string to per-node states for the 5-node bar. */
function deriveNodeStates(currentStage: string | null, events: PipelineEvent[]): PipelineNodeStatus[] {
  const nodes: { label: string; matchStages: string[] }[] = [
    { label: 'Ingestion',    matchStages: ['stage_1_complete'] },
    { label: 'Detection',    matchStages: ['stage_2_complete'] },
    { label: 'Analysis',     matchStages: ['stage_3_causal_engine_running', 'stage_3_complete'] },
    { label: 'Healing',      matchStages: ['stage_4_healing_executing', 'stage_4_healing_complete', 'stage_5_cooldown', 'stage_4_awaiting_approval'] },
    // Only include the in-progress stage here. Terminal stages (healing_complete,
    // healing_failed_*) are handled by the failed-flag check and currentIdx > nodeMaxIdx
    // logic, which correctly yields 'completed' / 'failed' without making the node 'active'.
    { label: 'Verification', matchStages: ['stage_6_verification_running'] },
  ];

  const stageOrder = [
    'stage_1_complete',
    'stage_2_complete',
    'stage_3_causal_engine_running',
    'stage_3_complete',
    'stage_4_healing_executing',
    'stage_4_healing_complete',
    'stage_4_awaiting_approval',
    'stage_5_cooldown',
    'stage_6_verification_running',
    'healing_complete',
    'healing_failed_escalated',
    'healing_failed_email_sent',
  ];

  const currentIdx = currentStage ? stageOrder.indexOf(currentStage) : -1;
  const failed = currentStage === 'healing_failed_escalated' || currentStage === 'healing_failed_email_sent';

  return nodes.map((node) => {
    // Find the most recent event matching this node's stages
    const nodeEvent = events.find(ev => node.matchStages.includes(ev.stage ?? ''));
    const timestamp = nodeEvent?.timestamp;

    const nodeMaxIdx = Math.max(...node.matchStages.map(s => stageOrder.indexOf(s)));
    if (currentIdx < 0) return { label: node.label, state: 'idle', timestamp };
    if (failed && node.label === 'Verification') return { label: node.label, state: 'failed', timestamp };
    if (currentIdx > nodeMaxIdx) return { label: node.label, state: 'completed', timestamp };
    if (node.matchStages.includes(currentStage ?? '')) return { label: node.label, state: 'active', timestamp };
    return { label: node.label, state: 'idle', timestamp };
  });
}

export function usePipelineEvents(enabled = true) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [stageTimestamp, setStageTimestamp] = useState<string | null>(null);
  const [stageHealingAction, setStageHealingAction] = useState<string | null>(null);
  const [nodeStates, setNodeStates] = useState<PipelineNodeStatus[]>(
    ['Ingestion', 'Detection', 'Analysis', 'Healing', 'Verification'].map(label => ({ label, state: 'idle' as NodeState }))
  );

  // Stage transition tracking for toast notifications
  const prevStageRef = useRef<string | null>(null);
  const { addToast } = useToast();

  // Incremented on every fetch; responses that arrive out-of-order are discarded.
  const fetchIdRef = useRef(0);

  const fetchEvents = useCallback(async () => {
    const fetchId = ++fetchIdRef.current;
    try {
      const [eventsRes, stageRes] = await Promise.allSettled([
        fetch('/api/v1/pipeline/events?limit=20'),
        fetch('/api/v1/pipeline/stage'),
      ]);

      // Discard stale response if a newer fetch has already resolved
      if (fetchId !== fetchIdRef.current) return;

      let fetchedEvents: PipelineEvent[] = [];
      if (eventsRes.status === 'fulfilled' && eventsRes.value.ok) {
        fetchedEvents = await eventsRes.value.json();
        setEvents(fetchedEvents);
      }

      if (stageRes.status === 'fulfilled' && stageRes.value.ok) {
        const stageData = await stageRes.value.json();
        const s: string | null = stageData?.stage ?? null;
        setCurrentStage(s);
        setStageTimestamp(stageData?.timestamp ?? null);
        setStageHealingAction(stageData?.healing_action ?? null);
        setNodeStates(deriveNodeStates(s, fetchedEvents));

        // ── Stage Transition Toast Notifications ──
        // Fire exactly ONE toast per stage change. Module-level _lastToastedStage
        // deduplicates across multiple hook instances (dashboard + visualizer both
        // mounted simultaneously) so the user never sees the same toast twice.
        if (s && s !== prevStageRef.current && s !== 'idle' && s !== 'unknown') {
          const prevStage = prevStageRef.current;
          prevStageRef.current = s;

          // Skip toast on initial page load to avoid stale notifications
          if (!prevStage) return;

          // Already toasted this stage from another hook instance — skip
          if (s === _lastToastedStage) return;
          _lastToastedStage = s;

          // First-ever healing notification (once per session, across all instances)
          if (s === 'stage_4_healing_executing' && !_firstHealShown) {
            _firstHealShown = true;
            addToast('🔧 First Healing Initiated — Autonomous remediation has begun', 'success');
            return;
          }

          const toastDef = STAGE_TOAST_MESSAGES[s];
          if (toastDef) {
            addToast(toastDef.message, toastDef.kind);
          }
        }

        // Track stage resetting to idle
        if ((!s || s === 'idle') && prevStageRef.current && prevStageRef.current !== 'idle' && prevStageRef.current !== 'unknown') {
          prevStageRef.current = s;
        }
      }
    } catch {
      // Non-fatal — silently ignore
    }
  }, [addToast]);

  // Poll every 1s during timed stages (cooldown / verification) for fast confirmation;
  // 2s otherwise. The interval is recreated whenever currentStage changes.
  const isTimedStage =
    currentStage === 'stage_5_cooldown' || currentStage === 'stage_6_verification_running';

  useEffect(() => {
    if (!enabled) return;
    fetchEvents();
    const id = setInterval(fetchEvents, isTimedStage ? 1000 : 2000);
    return () => clearInterval(id);
  }, [enabled, fetchEvents, isTimedStage]);

  const currentStageLabel =
    !currentStage || currentStage === 'idle' || currentStage === 'unknown'
      ? 'Waiting'
      : (STAGE_LABELS[currentStage] ?? 'Waiting');

  return { events, currentStage, currentStageLabel, nodeStates, stageTimestamp, stageHealingAction, refetch: fetchEvents };
}

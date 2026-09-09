/**
 * usePipelineEvents — Polls /api/v1/pipeline/events every 2s.
 * Returns the last N pipeline stage transition events and the current active stage label.
 * Used by PipelineProgressBar (Feature 4).
 */

import { useState, useEffect, useCallback } from 'react';
import type { PipelineEvent } from '../designSystem';

const STAGE_LABELS: Record<string, string> = {
  stage_1_complete: 'Ingestion',
  stage_2_complete: 'Detection',
  stage_3_causal_engine_running: 'Analysis',
  stage_3_complete: 'Analysis',
  stage_4_healing_executing: 'Healing',
  stage_4_healing_complete: 'Healing',
  healing_complete: 'Complete',
  healing_failed_escalated: 'Failed',
};

export type NodeState = 'idle' | 'active' | 'completed' | 'failed';

export interface PipelineNodeStatus {
  label: string;
  state: NodeState;
}

/** Maps the current pipeline stage string to per-node states for the 5-node bar. */
function deriveNodeStates(currentStage: string | null): PipelineNodeStatus[] {
  const nodes: { label: string; matchStages: string[] }[] = [
    { label: 'Ingestion',    matchStages: ['stage_1_complete'] },
    { label: 'Detection',    matchStages: ['stage_2_complete'] },
    { label: 'Analysis',     matchStages: ['stage_3_causal_engine_running', 'stage_3_complete'] },
    { label: 'Healing',      matchStages: ['stage_4_healing_executing', 'stage_4_healing_complete'] },
    { label: 'Verification', matchStages: ['healing_complete', 'healing_failed_escalated'] },
  ];

  const stageOrder = [
    'stage_1_complete',
    'stage_2_complete',
    'stage_3_causal_engine_running',
    'stage_3_complete',
    'stage_4_healing_executing',
    'stage_4_healing_complete',
    'healing_complete',
    'healing_failed_escalated',
  ];

  const currentIdx = currentStage ? stageOrder.indexOf(currentStage) : -1;
  const failed = currentStage === 'healing_failed_escalated';

  return nodes.map((node) => {
    const nodeMaxIdx = Math.max(...node.matchStages.map(s => stageOrder.indexOf(s)));
    if (currentIdx < 0) return { label: node.label, state: 'idle' };
    if (failed && node.label === 'Verification') return { label: node.label, state: 'failed' };
    if (currentIdx > nodeMaxIdx) return { label: node.label, state: 'completed' };
    if (node.matchStages.includes(currentStage ?? '')) return { label: node.label, state: 'active' };
    return { label: node.label, state: 'idle' };
  });
}

export function usePipelineEvents(enabled = true) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [nodeStates, setNodeStates] = useState<PipelineNodeStatus[]>(
    ['Ingestion', 'Detection', 'Analysis', 'Healing', 'Verification'].map(label => ({ label, state: 'idle' as NodeState }))
  );

  const fetchEvents = useCallback(async () => {
    try {
      const [eventsRes, stageRes] = await Promise.allSettled([
        fetch('/api/v1/pipeline/events?limit=8'),
        fetch('/api/v1/pipeline/stage'),
      ]);

      if (eventsRes.status === 'fulfilled' && eventsRes.value.ok) {
        const data: PipelineEvent[] = await eventsRes.value.json();
        setEvents(data);
      }

      if (stageRes.status === 'fulfilled' && stageRes.value.ok) {
        const stage = await stageRes.value.json();
        const s = stage?.stage ?? null;
        setCurrentStage(s);
        setNodeStates(deriveNodeStates(s));
      }
    } catch {
      // Non-fatal — silently ignore
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    fetchEvents();
    const id = setInterval(fetchEvents, 2000);
    return () => clearInterval(id);
  }, [enabled, fetchEvents]);

  const currentStageLabel = currentStage ? (STAGE_LABELS[currentStage] ?? 'Unknown') : 'Idle';

  return { events, currentStage, currentStageLabel, nodeStates };
}

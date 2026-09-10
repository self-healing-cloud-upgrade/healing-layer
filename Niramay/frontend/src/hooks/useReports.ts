/**
 * useReports — Manages report generation, history listing,
 * and polling for pending reports.
 * Calls POST /api/v1/reports/generate and GET /api/v1/reports.
 * Used by ReportsPage (Feature 3).
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { Report } from '../designSystem';

export interface GenerateReportPayload {
  report_type: 'incident_summary' | 'heal_summary' | 'full_pipeline';
  date_from: string;
  date_to: string;
  severities: string[];
  format: 'pdf' | 'json' | 'csv';
}

export function useReports() {
  const [reports, setReports] = useState<Report[]>([]);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const fetchReports = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/reports');
      if (res.ok) {
        const data: Report[] = await res.json();
        setReports(data);
        // Stop polling when no reports are pending
        const hasPending = data.some(r => r.status === 'pending');
        if (!hasPending && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = undefined;
        }
      }
    } catch { /* silent */ }
  }, []);

  const generate = useCallback(async (payload: GenerateReportPayload) => {
    setGenerating(true);
    setGenerateError(null);
    try {
      const res = await fetch('/api/v1/reports/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        setGenerateError(err.detail ?? 'Failed to start report');
        return false;
      }
      await fetchReports();
      // Start polling for status changes
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchReports, 10_000);
      }
      return true;
    } catch (e: unknown) {
      setGenerateError(e instanceof Error ? e.message : 'Network error');
      return false;
    } finally {
      setGenerating(false);
    }
  }, [fetchReports]);

  /** Download a ready report — triggers browser file download. */
  const download = useCallback((reportId: string) => {
    const a = document.createElement('a');
    a.href = `/api/v1/reports/${reportId}/download`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, []);

  useEffect(() => {
    fetchReports();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchReports]);

  return { reports, generating, generateError, generate, download, refetch: fetchReports };
}

/**
 * useLogs — Paginated log fetching with debounced keyword search,
 * level multi-select, and time-range filter.
 * Calls GET /api/v1/logs/raw and GET /api/v1/logs/normalized.
 * Used by LogsPanel (Feature 1).
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { LogPage, RawLogHit, NormalizedLogHit } from '../designSystem';

export type LogTab = 'raw' | 'normalized';
export type TimeRange = '1h' | '6h' | '24h' | 'custom';

export interface LogFilters {
  keyword: string;
  levels: string[];          // e.g. ['ERROR', 'WARN']
  timeRange: TimeRange;
  customFrom: string;        // ISO string, only used when timeRange='custom'
  customTo: string;
}

function timeRangeToParams(filters: LogFilters): Record<string, string> {
  const now = new Date();
  const params: Record<string, string> = {};
  if (filters.timeRange === 'custom') {
    if (filters.customFrom) params.from = filters.customFrom;
    if (filters.customTo) params.to = filters.customTo;
  } else {
    const hours = filters.timeRange === '1h' ? 1 : filters.timeRange === '6h' ? 6 : 24;
    params.from = new Date(now.getTime() - hours * 3600_000).toISOString();
    params.to = now.toISOString();
  }
  return params;
}

export function useRawLogs(filters: LogFilters, page: number, size = 50) {
  const [data, setData] = useState<LogPage<RawLogHit>>({ total: 0, page: 1, size, hits: [] });
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const fetch_ = useCallback(async (f: LogFilters, p: number) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(p),
        size: String(size),
        ...timeRangeToParams(f),
      });
      if (f.keyword) params.set('keyword', f.keyword);
      if (f.levels.length) params.set('level', f.levels.join(','));
      const res = await fetch(`/api/v1/logs/raw?${params}`);
      if (res.ok) setData(await res.json());
    } catch { /* silent */ }
    setLoading(false);
  }, [size]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetch_(filters, page), 300);
    return () => clearTimeout(debounceRef.current);
  }, [filters, page, fetch_]);

  return { data, loading, refetch: () => fetch_(filters, page) };
}

export function useNormalizedLogs(filters: LogFilters, page: number, size = 50, anomalyThreshold = 0.4) {
  const [data, setData] = useState<LogPage<NormalizedLogHit>>({ total: 0, page: 1, size, hits: [] });
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const fetch_ = useCallback(async (f: LogFilters, p: number) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(p),
        size: String(size),
        ...timeRangeToParams(f),
      });
      if (f.keyword) params.set('keyword', f.keyword);
      if (f.levels.length) params.set('level', f.levels.join(','));
      const res = await fetch(`/api/v1/logs/normalized?${params}`);
      if (res.ok) setData(await res.json());
    } catch { /* silent */ }
    setLoading(false);
  }, [size, anomalyThreshold]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetch_(filters, page), 300);
    return () => clearTimeout(debounceRef.current);
  }, [filters, page, fetch_]);

  return { data, loading, refetch: () => fetch_(filters, page) };
}

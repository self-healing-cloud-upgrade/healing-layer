/**
 * useArtifacts — Polls /api/v1/artifacts/counts every 30s.
 * Provides refetchCard() for per-card manual refresh.
 * Used by PipelineArtifactCards (Feature 2).
 */

import { useState, useEffect, useCallback } from 'react';
import type { ArtifactCard } from '../designSystem';

export function useArtifacts() {
  const [cards, setCards] = useState<ArtifactCard[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchCounts = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/artifacts/counts');
      if (res.ok) setCards(await res.json());
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchCounts();
    const id = setInterval(fetchCounts, 30_000);
    return () => clearInterval(id);
  }, [fetchCounts]);

  return { cards, loading, refetch: fetchCounts };
}

/**
 * useArtifactRecords — Fetches paginated records for a single artifact index.
 * Called when a card is clicked to open the side drawer.
 */
export function useArtifactRecords(
  artifactKey: string | null,
  page: number,
  keyword: string
) {
  const [data, setData] = useState<{ total: number; hits: Record<string, unknown>[] }>({ total: 0, hits: [] });
  const [loading, setLoading] = useState(false);

  const fetch_ = useCallback(async () => {
    if (!artifactKey) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), size: '50' });
      if (keyword) params.set('keyword', keyword);
      const res = await fetch(`/api/v1/artifacts/${artifactKey}/records?${params}`);
      if (res.ok) setData(await res.json());
    } catch { /* silent */ }
    setLoading(false);
  }, [artifactKey, page, keyword]);

  useEffect(() => { fetch_(); }, [fetch_]);

  return { data, loading, refetch: fetch_ };
}

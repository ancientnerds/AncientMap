import { useState, useEffect, useCallback } from 'react';

export interface StepData {
  count: number;
  elapsed: number;
  status: 'done' | 'fail' | 'skip' | 'run';
  error?: string;
}

export interface PipelineStatus {
  pipeline: string;
  status: 'online' | 'offline';
  last_heartbeat: string | null;
  last_cycle_ok: boolean;
  total_elapsed: number | null;
  steps: Record<string, StepData>;
}

export function usePipelineStatus(pipeline: 'news' | 'radar' | 'article', pollInterval = 60000) {
  const [data, setData] = useState<PipelineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/news/pipeline-status?pipeline=${pipeline}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: PipelineStatus = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fetch failed');
    } finally {
      setLoading(false);
    }
  }, [pipeline]);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, pollInterval);
    return () => clearInterval(id);
  }, [fetchStatus, pollInterval]);

  return { data, error, loading };
}

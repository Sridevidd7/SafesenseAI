/**
 * useDashboardStats.ts
 * Fetches live dashboard data from GET /api/dashboard/stats.
 * Exposes an idempotent `refresh()` function that re-fetches without mutating data.
 */
import { useState, useEffect, useCallback } from 'react';
import { fetchDashboardStats, DashboardStats } from '../services/api';

interface UseDashboardStats {
  stats:      DashboardStats | null;
  loading:    boolean;
  refreshing: boolean;
  error:      string | null;
  refresh:    () => Promise<DashboardStats | null>;
}

export function useDashboardStats(): UseDashboardStats {
  const [stats,      setStats]      = useState<DashboardStats | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const loadData = useCallback(async (isInitial = false): Promise<DashboardStats | null> => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const data = await fetchDashboardStats();
      setStats(data);
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Backend unavailable';
      setError(msg);
      if (isInitial) {
        setStats(null);
      }
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const refresh = useCallback(() => {
    return loadData(false);
  }, [loadData]);

  useEffect(() => {
    loadData(true);
  }, [loadData]);

  useEffect(() => {
    const handleUpdate = () => {
      loadData(false);
    };
    window.addEventListener('safesense:data-updated', handleUpdate);
    return () => window.removeEventListener('safesense:data-updated', handleUpdate);
  }, [loadData]);

  return { stats, loading, refreshing, error, refresh };
}


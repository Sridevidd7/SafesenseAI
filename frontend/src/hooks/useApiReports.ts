/**
 * useApiReports.ts
 * Fetches the persisted reports list from GET /api/reports.
 * Exposes an idempotent `refresh()` to reload from the backend without mutating data.
 */
import { useState, useEffect, useCallback } from 'react';
import { fetchReports, ApiReport, ReportsListResponse } from '../services/api';

interface UseApiReports {
  reports:    ApiReport[];
  total:      number;
  loading:    boolean;
  refreshing: boolean;
  error:      string | null;
  refresh:    () => Promise<ReportsListResponse | null>;
}

export function useApiReports(): UseApiReports {
  const [reports,    setReports]    = useState<ApiReport[]>([]);
  const [total,      setTotal]      = useState(0);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const loadData = useCallback(async (isInitial = false): Promise<ReportsListResponse | null> => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const data = await fetchReports();
      setReports(data.reports);
      setTotal(data.total);
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Backend unavailable';
      setError(msg);
      if (isInitial) {
        setReports([]);
        setTotal(0);
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

  return { reports, total, loading, refreshing, error, refresh };
}


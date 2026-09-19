import { useState, useEffect, useCallback } from 'react';
import EmptyState from '../components/EmptyState';
import { RiskBadge } from '../components/RiskBadge';
import { fetchAnalyticsPatterns, PatternItem } from '../services/api';
import { GitBranch, MapPin, RefreshCw } from 'lucide-react';

export default function SafetyPatternsPage() {
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPatterns = useCallback(async (isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(false);
    }
    setError(null);

    try {
      const data = await fetchAnalyticsPatterns();
      setPatterns(Array.isArray(data) ? data : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch patterns';
      console.error('Safety patterns fetch error:', err);
      setError(msg);
      if (isInitial) setPatterns([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadPatterns(true);
  }, [loadPatterns]);

  useEffect(() => {
    const handleUpdate = () => loadPatterns(false);
    window.addEventListener('safesense:data-updated', handleUpdate);
    return () => window.removeEventListener('safesense:data-updated', handleUpdate);
  }, [loadPatterns]);

  if (loading && patterns.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-sm font-medium text-slate-600">Analyzing recurring safety patterns...</p>
        </div>
      </div>
    );
  }

  if (!loading && patterns.length === 0 && !error) {
    return <EmptyState />;
  }

  return (
    <div className="space-y-8 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="section-title">Safety Patterns</h1>
          <p className="section-sub">Recurring safety failure patterns discovered across all database records using rule-based clustering.</p>
        </div>
        <button
          onClick={() => loadPatterns(false)}
          disabled={refreshing || loading}
          className="btn-secondary text-xs flex items-center gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          {error}
        </div>
      )}

      {patterns.length === 0 ? (
        <div className="card text-slate-500 text-sm">
          No significant recurring patterns detected. This may indicate low report volume or high variation in report types.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-5">
          {patterns.map((pattern, idx) => (
            <div key={pattern.name || pattern.category || idx} className="card-hover">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center flex-shrink-0">
                    <GitBranch className="w-4 h-4" />
                  </div>
                  <h3 className="font-bold text-slate-900 text-sm">{pattern.name || pattern.category}</h3>
                </div>
                <RiskBadge level={(pattern.risk_level as any) || 'MEDIUM'} size="sm" />
              </div>
              <p className="text-slate-600 text-xs mb-4 leading-relaxed">
                {pattern.description || `Precursor pattern identified in ${pattern.category} category.`}
              </p>
              <div className="grid grid-cols-3 gap-2.5 text-center mb-4">
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 shadow-2xs">
                  <div className="text-lg font-bold text-slate-900">{pattern.count || pattern.frequency || 0}</div>
                  <div className="text-xs text-slate-500 font-medium">Reports</div>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 shadow-2xs">
                  <div className="text-lg font-bold text-blue-600">{pattern.sites?.length || 1}</div>
                  <div className="text-xs text-slate-500 font-medium">Sites</div>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 shadow-2xs">
                  <div className={`text-lg font-bold ${pattern.trend === 'increasing' ? 'text-red-600' : pattern.trend === 'stable' ? 'text-amber-600' : 'text-green-600'}`}>
                    {pattern.trend === 'increasing' ? '↑' : pattern.trend === 'stable' ? '→' : '↓'}
                  </div>
                  <div className="text-xs text-slate-500 font-medium capitalize">{pattern.trend || 'stable'}</div>
                </div>
              </div>
              {pattern.sites && pattern.sites.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-100">
                  <MapPin className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                  {pattern.sites.slice(0, 3).map(site => (
                    <span key={site} className="text-xs bg-slate-100 text-slate-700 font-medium px-2 py-0.5 rounded-md">{site}</span>
                  ))}
                  {pattern.sites.length > 3 && <span className="text-xs text-slate-400 font-medium">+{pattern.sites.length - 3} more</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


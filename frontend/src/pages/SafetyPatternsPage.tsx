import { useState, useEffect, useCallback } from 'react';
import EmptyState from '../components/EmptyState';
import { RiskBadge } from '../components/RiskBadge';
import { fetchAnalyticsPatterns, fetchAnalyticsInsights, PatternItem, AIInsight } from '../services/api';
import { GitBranch, MapPin, RefreshCw, Sparkles, AlertOctagon, TrendingUp, ShieldAlert, Repeat } from 'lucide-react';

export default function SafetyPatternsPage() {
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async (isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const [patternsData, insightsData] = await Promise.all([
        fetchAnalyticsPatterns(),
        fetchAnalyticsInsights().catch(() => [] as AIInsight[]),
      ]);
      setPatterns(Array.isArray(patternsData) ? patternsData : []);
      setInsights(Array.isArray(insightsData) ? insightsData : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch patterns';
      console.error('Safety patterns fetch error:', err);
      setError(msg);
      if (isInitial) {
        setPatterns([]);
        setInsights([]);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData(true);
  }, [loadData]);

  useEffect(() => {
    const handleUpdate = () => loadData(false);
    window.addEventListener('safesense:data-updated', handleUpdate);
    return () => window.removeEventListener('safesense:data-updated', handleUpdate);
  }, [loadData]);

  // ─── Loading State ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-sm font-medium text-slate-600">Running Pattern Intelligence & Similarity Clustering...</p>
        </div>
      </div>
    );
  }

  // ─── Error State ───────────────────────────────────────────────────────────
  if (error && patterns.length === 0) {
    return (
      <div className="card border-red-200 bg-red-50/50 p-8 text-center max-w-lg mx-auto my-12 space-y-4">
        <h3 className="text-lg font-bold text-slate-900">Failed to Load Safety Patterns</h3>
        <p className="text-xs text-red-700">{error}</p>
        <button onClick={() => loadData(true)} className="btn-primary mx-auto text-xs">
          <RefreshCw className="w-3.5 h-3.5" /> Retry
        </button>
      </div>
    );
  }

  // ─── Empty State ───────────────────────────────────────────────────────────
  if (patterns.length === 0) {
    return (
      <EmptyState
        title="No Safety Patterns Available"
        message="Upload a safety dataset to automatically analyze and cluster recurring hazard patterns."
      />
    );
  }

  return (
    <div className="space-y-8 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="section-title">Pattern Intelligence & Insights</h1>
            <span className="bg-indigo-100 text-indigo-800 text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-indigo-600" /> Insight Engine
            </span>
          </div>
          <p className="section-sub">Similarity-based incident clustering, repeated failure detection, and cross-site anomaly intelligence.</p>
        </div>
        <button
          onClick={() => loadData(false)}
          disabled={refreshing || loading}
          className="btn-secondary text-xs flex items-center gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* ─── AI Insights Section ───────────────────────────────────────────── */}
      {insights.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">AI Safety Insights</h2>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            {insights.map((insight, idx) => {
              const isAnomaly = insight.type === 'ANOMALY';
              const isCrossSite = insight.type === 'CROSS_SITE_RISK';
              const isRecurring = insight.type === 'RECURRING_PATTERN';
              
              const borderClass = isAnomaly
                ? 'border-red-300 bg-red-50/60'
                : isCrossSite
                ? 'border-amber-300 bg-amber-50/60'
                : 'border-indigo-200 bg-indigo-50/40';

              const icon = isAnomaly ? (
                <AlertOctagon className="w-4 h-4 text-red-600 flex-shrink-0" />
              ) : isCrossSite ? (
                <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0" />
              ) : isRecurring ? (
                <Repeat className="w-4 h-4 text-indigo-600 flex-shrink-0" />
              ) : (
                <TrendingUp className="w-4 h-4 text-blue-600 flex-shrink-0" />
              );

              return (
                <div key={idx} className={`p-4 rounded-xl border ${borderClass} flex items-start gap-3 shadow-2xs`}>
                  <div className="mt-0.5">{icon}</div>
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h4 className="text-xs font-bold text-slate-900">{insight.title}</h4>
                      <RiskBadge level={(insight.severity as any) || 'HIGH'} size="sm" />
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed">{insight.message}</p>
                    {insight.metric && (
                      <span className="inline-block text-[11px] font-semibold text-slate-500 bg-white/80 px-2 py-0.5 rounded border border-slate-200/80">
                        {insight.metric}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── Pattern Clusters ──────────────────────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-slate-700" />
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Discovered Similarity Clusters ({patterns.length})</h2>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-5">
          {patterns.map((pattern, idx) => (
            <div key={pattern.cluster_id || pattern.name || idx} className="card-hover">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2 flex-wrap">
                  {pattern.cluster_id && (
                    <span className="text-[11px] font-mono font-bold bg-slate-900 text-white px-2 py-0.5 rounded">
                      {pattern.cluster_id}
                    </span>
                  )}
                  <h3 className="font-bold text-slate-900 text-sm">{pattern.theme || pattern.name || pattern.category}</h3>
                  {pattern.is_repeated && (
                    <span className="bg-amber-100 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
                      <Repeat className="w-2.5 h-2.5" /> Recurring Pattern
                    </span>
                  )}
                </div>
                <RiskBadge level={(pattern.risk_level as any) || 'MEDIUM'} size="sm" />
              </div>

              <p className="text-slate-600 text-xs mb-3 leading-relaxed">
                {pattern.description || `Precursor pattern identified in ${pattern.category} category.`}
              </p>

              {pattern.sample_descriptions && pattern.sample_descriptions.length > 0 && (
                <div className="bg-slate-50 border border-slate-100 rounded-lg p-2.5 mb-3 text-[11px] text-slate-600 italic space-y-1">
                  <span className="font-semibold not-italic text-slate-500 block text-[10px] uppercase">Representative Observations:</span>
                  {pattern.sample_descriptions.slice(0, 2).map((sample, sIdx) => (
                    <div key={sIdx} className="truncate">"{sample}"</div>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-3 gap-2.5 text-center mb-4">
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 shadow-2xs">
                  <div className="text-lg font-bold text-slate-900">{pattern.count || pattern.frequency || 0}</div>
                  <div className="text-xs text-slate-500 font-medium">Incidents</div>
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
      </div>
    </div>
  );
}



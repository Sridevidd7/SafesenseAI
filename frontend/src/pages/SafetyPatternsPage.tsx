/**
 * SafetyPatternsPage.tsx — SafeSense AI Pattern Intelligence & Incident Similarity Clustering
 *
 * Sourced directly from backend Pattern Intelligence:
 * - GET /api/analytics/patterns
 * - GET /api/analytics/insights
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  GitBranch, MapPin, RefreshCw, Sparkles, AlertOctagon, TrendingUp,
  TrendingDown, Minus, ShieldAlert, Repeat, Search, Filter, X, Eye,
  CheckCircle2, ArrowUpDown
} from 'lucide-react';

import EmptyState from '../components/EmptyState';
import ErrorState from '../components/ErrorState';
import { RiskBadge, SIFBadge } from '../components/RiskBadge';
import PatternDetailModal from '../components/PatternDetailModal';
import KpiCard from '../components/KpiCard';

import {
  fetchPatternIntelligence,
  fetchAnalyticsInsights,
  PatternItem,
  AIInsight,
} from '../services/api';

export default function SafetyPatternsPage() {
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [repeatedFailures, setRepeatedFailures] = useState<PatternItem[]>([]);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal inspection state
  const [selectedPattern, setSelectedPattern] = useState<PatternItem | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [selectedRisk, setSelectedRisk] = useState<string>('ALL');
  const [recurringOnly, setRecurringOnly] = useState(false);
  const [sifOnly, setSifOnly] = useState(false);
  const [sortBy, setSortBy] = useState<'frequency' | 'sif' | 'risk'>('frequency');

  const loadData = useCallback(async (isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const [patternsEnvelope, insightsData] = await Promise.all([
        fetchPatternIntelligence(),
        fetchAnalyticsInsights().catch(() => [] as AIInsight[]),
      ]);

      const clusterList = patternsEnvelope.data || [];
      setPatterns(clusterList);
      setRepeatedFailures(patternsEnvelope.repeated_failures || []);

      const combinedInsights = [...(patternsEnvelope.insights || []), ...(insightsData || [])];
      const uniqueInsights = Array.from(
        new Map(combinedInsights.map(item => [item.title + item.message, item])).values()
      );
      setInsights(uniqueInsights);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch pattern intelligence';
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

  // Unique categories for filter dropdown
  const availableCategories = useMemo(() => {
    const set = new Set<string>();
    patterns.forEach(p => {
      if (p.category) set.add(p.category);
    });
    return Array.from(set).sort();
  }, [patterns]);

  // Filtered and sorted patterns
  const filteredPatterns = useMemo(() => {
    let result = [...patterns];

    // Search query
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      result = result.filter(p => {
        const theme = (p.theme || p.name || '').toLowerCase();
        const cat = (p.category || '').toLowerCase();
        const bar = (p.barrier || '').toLowerCase();
        const desc = (p.description || p.simplified_insight || '').toLowerCase();
        const sites = (p.sites || []).join(' ').toLowerCase();
        const samples = (p.sample_descriptions || []).join(' ').toLowerCase();
        const id = (p.cluster_id || '').toLowerCase();
        return (
          theme.includes(q) ||
          cat.includes(q) ||
          bar.includes(q) ||
          desc.includes(q) ||
          sites.includes(q) ||
          samples.includes(q) ||
          id.includes(q)
        );
      });
    }

    // Category filter
    if (selectedCategory !== 'ALL') {
      result = result.filter(p => p.category === selectedCategory);
    }

    // Risk level filter
    if (selectedRisk !== 'ALL') {
      result = result.filter(p => (p.risk_level || '').toUpperCase() === selectedRisk);
    }

    // Recurring only filter (>= 3 reports)
    if (recurringOnly) {
      result = result.filter(p => p.is_repeated || (p.count || p.frequency || 0) >= 3);
    }

    // SIF only filter
    if (sifOnly) {
      result = result.filter(p => (p.sif_count || 0) > 0);
    }

    // Sort order
    result.sort((a, b) => {
      if (sortBy === 'sif') {
        return (b.sif_count || 0) - (a.sif_count || 0);
      }
      if (sortBy === 'risk') {
        return (b.risk_score || b.avg_risk || 0) - (a.risk_score || a.avg_risk || 0);
      }
      return (b.count || b.frequency || 0) - (a.count || a.frequency || 0);
    });

    return result;
  }, [patterns, searchTerm, selectedCategory, selectedRisk, recurringOnly, sifOnly, sortBy]);

  // Aggregate summary metrics
  const totalClusters = patterns.length;
  const recurringCount = patterns.filter(p => p.is_repeated || (p.count || 0) >= 3).length;
  const sifClusterCount = patterns.filter(p => (p.sif_count || 0) > 0).length;
  const crossSiteCount = patterns.filter(p => (p.sites || []).length > 1).length;

  // ── Loading State ─────────────────────────────────────────────────────────
  if (loading && patterns.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[420px]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-sm font-semibold text-slate-700">Running Pattern Intelligence Clustering...</p>
          <p className="text-xs text-slate-500">Evaluating token similarity, barrier failures, and recurring pre-cursors</p>
        </div>
      </div>
    );
  }

  // ── Error State ───────────────────────────────────────────────────────────
  if (error && patterns.length === 0) {
    return (
      <div className="py-8">
        <ErrorState
          title="Failed to Load Safety Patterns"
          message={error}
          hint="Make sure the backend is running and the analytics service has initialized pattern clusters."
          onRetry={() => loadData(true)}
          retrying={loading}
        />
      </div>
    );
  }

  // ── Empty State ───────────────────────────────────────────────────────────
  if (patterns.length === 0) {
    return (
      <EmptyState
        title="No Safety Patterns Discovered"
        message="Upload a safety dataset to automatically analyze and cluster recurring hazard patterns."
      />
    );
  }

  return (
    <div className="space-y-8 animate-in relative">
      {/* Pattern Detail Modal */}
      <PatternDetailModal
        pattern={selectedPattern}
        onClose={() => setSelectedPattern(null)}
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="section-title">Pattern Intelligence &amp; Recurring Failures</h1>
            <span className="bg-indigo-100 text-indigo-900 border border-indigo-200 text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-indigo-600" />
              Similarity Engine
            </span>
          </div>
          <p className="section-sub">
            Single-pass similarity clustering, recurring barrier failures, and cross-site anomaly intelligence across stored observations.
          </p>
        </div>

        <button
          onClick={() => loadData(false)}
          disabled={refreshing || loading}
          className="btn-secondary text-xs flex items-center gap-2 self-start sm:self-auto"
          title="Re-run similarity clustering across database"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
          <span>{refreshing ? 'Analyzing...' : 'Refresh Patterns'}</span>
        </button>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Discovered Clusters"
          value={totalClusters}
          subtext="Similarity-grouped patterns"
          icon={GitBranch}
          variant="indigo"
        />

        <KpiCard
          label="Recurring Failures"
          value={recurringCount}
          subtext="Clusters with ≥3 incidents"
          icon={Repeat}
          variant="amber"
          badge="REPEATED"
        />

        <KpiCard
          label="SIF Precursors"
          value={sifClusterCount}
          subtext="Clusters with SIF potential"
          icon={AlertOctagon}
          variant="red"
          badge="SIF: YES"
        />

        <KpiCard
          label="Cross-Site Risks"
          value={crossSiteCount}
          subtext="Multi-facility occurrence"
          icon={MapPin}
          variant="blue"
        />
      </div>

      {/* ── AI Safety Insights & Anomalies ─────────────────────────────────── */}
      {insights.length > 0 && (
        <section aria-labelledby="insights-heading" className="space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            <h2 id="insights-heading" className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Pattern Intelligence Synthesized Insights ({insights.length})
            </h2>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {insights.map((insight, idx) => {
              const isAnomaly = insight.type === 'ANOMALY';
              const isCrossSite = insight.type === 'CROSS_SITE_RISK';
              const isRecurring = insight.type === 'RECURRING_PATTERN';

              const borderClass = isAnomaly
                ? 'border-red-300 bg-red-50/70 text-red-950'
                : isCrossSite
                ? 'border-amber-300 bg-amber-50/70 text-amber-950'
                : 'border-indigo-200 bg-indigo-50/50 text-indigo-950';

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
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <h3 className="text-xs font-bold truncate">{insight.title}</h3>
                      <RiskBadge level={insight.severity || 'HIGH'} size="sm" showIcon={false} />
                    </div>
                    <p className="text-xs text-slate-700 leading-relaxed">{insight.message}</p>
                    {insight.metric && (
                      <span className="inline-block text-[11px] font-semibold text-slate-600 bg-white/90 px-2 py-0.5 rounded border border-slate-200/80">
                        {insight.metric}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Filter Bar ─────────────────────────────────────────────────────── */}
      <div className="card p-4 space-y-3.5 bg-white border-slate-200">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          {/* Search box */}
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search by pattern theme, failed barrier, site, or keyword..."
              className="input-field pl-9 text-xs w-full"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Category Dropdown */}
          <div className="flex items-center gap-2">
            <select
              value={selectedCategory}
              onChange={e => setSelectedCategory(e.target.value)}
              className="input-field text-xs py-1.5 px-3 min-w-[170px]"
            >
              <option value="ALL">All Life-Saving Rules</option>
              {availableCategories.map(cat => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>

            {/* Sort Dropdown */}
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value as any)}
              className="input-field text-xs py-1.5 px-3 min-w-[140px]"
            >
              <option value="frequency">Sort: Frequency (High)</option>
              <option value="sif">Sort: SIF Potential</option>
              <option value="risk">Sort: Risk Score</option>
            </select>
          </div>
        </div>

        {/* Quick Toggles Row */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-500 font-semibold text-[11px] uppercase mr-1">Risk Filter:</span>
            {(['ALL', 'CRITICAL', 'HIGH', 'MEDIUM'] as const).map(lvl => (
              <button
                key={lvl}
                onClick={() => setSelectedRisk(lvl)}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                  selectedRisk === lvl
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {lvl}
              </button>
            ))}

            <div className="h-4 w-px bg-slate-200 mx-1 hidden sm:block" />

            {/* Recurring Toggle */}
            <button
              onClick={() => setRecurringOnly(!recurringOnly)}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold border flex items-center gap-1.5 transition-colors ${
                recurringOnly
                  ? 'bg-amber-100 text-amber-900 border-amber-300 font-bold'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <Repeat className="w-3 h-3 text-amber-600" />
              Recurring Only (≥3)
            </button>

            {/* SIF Toggle */}
            <button
              onClick={() => setSifOnly(!sifOnly)}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold border flex items-center gap-1.5 transition-colors ${
                sifOnly
                  ? 'bg-red-100 text-red-900 border-red-300 font-bold'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <AlertOctagon className="w-3 h-3 text-red-600" />
              SIF Precursors Only
            </button>
          </div>

          <div className="text-xs text-slate-500 font-medium">
            Showing <strong className="text-slate-800">{filteredPatterns.length}</strong> of {patterns.length} clusters
          </div>
        </div>
      </div>

      {/* ── Pattern Cards Grid ─────────────────────────────────────────────── */}
      {filteredPatterns.length === 0 ? (
        <div className="card p-12 text-center text-slate-500 text-xs">
          No safety patterns match the selected filters. Try broadening your search or resetting filters.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-5">
          {filteredPatterns.map((pattern, idx) => {
            const count = pattern.count || pattern.frequency || 0;
            const sifCount = pattern.sif_count || 0;
            const trend = pattern.trend || 'stable';

            return (
              <div
                key={pattern.cluster_id || pattern.name || idx}
                onClick={() => setSelectedPattern(pattern)}
                className="card-hover flex flex-col justify-between cursor-pointer border border-slate-200 hover:border-blue-400 hover:shadow-md transition-all p-5"
              >
                <div>
                  {/* Top Bar: Cluster ID, Badges */}
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      {pattern.cluster_id && (
                        <span className="text-[11px] font-mono font-bold bg-slate-900 text-white px-2 py-0.5 rounded">
                          {pattern.cluster_id}
                        </span>
                      )}
                      <RiskBadge level={pattern.risk_level || 'MEDIUM'} size="sm" />
                      {sifCount > 0 ? (
                        <SIFBadge potential="YES" size="sm" />
                      ) : (
                        <SIFBadge potential="NO" size="sm" />
                      )}
                      {pattern.is_repeated && (
                        <span className="bg-amber-100 text-amber-900 border border-amber-300 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
                          <Repeat className="w-2.5 h-2.5 text-amber-700" /> Recurring
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Pattern Theme */}
                  <h3 className="font-bold text-slate-900 text-sm mb-1.5 leading-snug">
                    {pattern.theme || pattern.name || pattern.category}
                  </h3>

                  {/* What is recurring description */}
                  <p className="text-slate-600 text-xs mb-3.5 leading-relaxed">
                    {pattern.simplified_insight || pattern.description || `Precursor pattern identified in ${pattern.category}.`}
                  </p>

                  {/* Representative Sample Observation Excerpts */}
                  {pattern.sample_descriptions && pattern.sample_descriptions.length > 0 && (
                    <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-2.5 mb-3.5 text-[11px] text-slate-700 italic space-y-1">
                      <span className="font-bold not-italic text-slate-500 block text-[10px] uppercase">
                        Evidence Excerpt:
                      </span>
                      <div className="truncate">"{pattern.sample_descriptions[0]}"</div>
                    </div>
                  )}
                </div>

                <div>
                  {/* 4-Metric Grid */}
                  <div className="grid grid-cols-4 gap-2 text-center mb-3.5 pt-2 border-t border-slate-100">
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2">
                      <div className="text-base font-bold text-slate-900">{count}</div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase">Reports</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2">
                      <div className={`text-base font-bold ${sifCount > 0 ? 'text-red-600' : 'text-slate-700'}`}>
                        {sifCount}
                      </div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase">SIF</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2">
                      <div className="text-base font-bold text-blue-700">{pattern.sites?.length || 1}</div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase">Sites</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-2">
                      <div className="flex items-center justify-center gap-0.5">
                        {trend === 'increasing' ? (
                          <TrendingUp className="w-3.5 h-3.5 text-red-600" />
                        ) : trend === 'decreasing' ? (
                          <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
                        ) : (
                          <Minus className="w-3.5 h-3.5 text-slate-500" />
                        )}
                        <span className={`text-xs font-bold capitalize ${
                          trend === 'increasing' ? 'text-red-600' : trend === 'decreasing' ? 'text-emerald-600' : 'text-slate-700'
                        }`}>
                          {trend}
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase">Trend</div>
                    </div>
                  </div>

                  {/* Footer: Sites & Inspect Button */}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
                    {pattern.sites && pattern.sites.length > 0 ? (
                      <div className="flex items-center gap-1.5 flex-wrap min-w-0 flex-1 mr-2">
                        <MapPin className="w-3 h-3 text-slate-400 shrink-0" />
                        {pattern.sites.slice(0, 2).map(site => (
                          <span key={site} className="text-[11px] bg-slate-100 text-slate-700 font-medium px-1.5 py-0.2 rounded truncate">
                            {site}
                          </span>
                        ))}
                        {pattern.sites.length > 2 && (
                          <span className="text-[10px] text-slate-500 font-semibold">
                            +{pattern.sites.length - 2} more
                          </span>
                        )}
                      </div>
                    ) : (
                      <div />
                    )}

                    <span className="text-xs font-bold text-blue-600 inline-flex items-center gap-1 shrink-0">
                      <Eye className="w-3.5 h-3.5" /> Inspect
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

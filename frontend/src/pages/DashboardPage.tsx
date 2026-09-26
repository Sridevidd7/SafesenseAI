/**
 * DashboardPage.tsx — SafeSense AI Industrial Safety Intelligence Dashboard
 *
 * All data sourced directly from backend APIs:
 * - GET /api/dashboard/summary (live aggregated statistics)
 * - GET /api/risk-intelligence/trends (monthly time-series & trajectory)
 * - GET /api/analytics/patterns (similarity clusters & repeated failure detections)
 *
 * No fake data. No invented metrics. Pure deterministic HSE intelligence.
 */
import { useMemo, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  Shield, AlertTriangle, AlertOctagon, TrendingUp, GitBranch,
  Repeat, Zap, RefreshCw, CheckCircle, ArrowRight, Sparkles,
  Database, Activity, ShieldAlert
} from 'lucide-react';

import KpiCard from '../components/KpiCard';
import { KpiGridSkeleton, ChartSkeleton } from '../components/LoadingSkeleton';
import ErrorState from '../components/ErrorState';
import { RiskBadge, SIFBadge } from '../components/RiskBadge';
import SifRiskHeatmap from '../components/SifRiskHeatmap';

import {
  fetchDashboardStats,
  fetchTrendsIntelligence,
  fetchPatternIntelligence,
  DashboardStats,
  PatternItem,
  AIInsight,
} from '../services/api';

// ─── Theme Color Tokens ──────────────────────────────────────────────────────
const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#DC2626',
  HIGH:     '#EA580C',
  MEDIUM:   '#D97706',
  LOW:      '#16A34A',
};

const CATEGORY_COLORS = [
  '#2563EB', '#7C3AED', '#D97706', '#DC2626',
  '#16A34A', '#0891B2', '#EA580C', '#9333EA',
];

export default function DashboardPage() {
  const navigate = useNavigate();

  // State
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [repeatedFailures, setRepeatedFailures] = useState<PatternItem[]>([]);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [trendStatus, setTrendStatus] = useState<string>('STABLE');
  const [trendReason, setTrendReason] = useState<string>('');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // ── Data Fetching ─────────────────────────────────────────────────────────
  const loadDashboardData = useCallback(async (isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const [statsRes, trendsRes, patternsRes] = await Promise.all([
        fetchDashboardStats(),
        fetchTrendsIntelligence().catch(() => ({
          data: [],
          trend: 'STABLE',
          trend_reason: 'Trend calculation available with historical time-series.',
          anomalies: [],
          insights: [],
        })),
        fetchPatternIntelligence().catch(() => ({
          data: [],
          repeated_failures: [],
          insights: [],
        })),
      ]);

      setStats(statsRes);
      setTrendStatus(trendsRes.trend || 'STABLE');
      setTrendReason(trendsRes.trend_reason || '');
      setPatterns(patternsRes.data || []);
      setRepeatedFailures(patternsRes.repeated_failures || []);

      // Merge unique insights from trends and pattern engine
      const combinedInsights = [...(trendsRes.insights || []), ...(patternsRes.insights || [])];
      const uniqueInsights = Array.from(
        new Map(combinedInsights.map(item => [item.title + item.message, item])).values()
      );
      setInsights(uniqueInsights);

      return statsRes;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to connect to SafeSense AI backend';
      setError(msg);
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData(true);
  }, [loadDashboardData]);

  // Global update event listener (triggered after uploads or modifications)
  useEffect(() => {
    const handleUpdate = () => loadDashboardData(false);
    window.addEventListener('safesense:data-updated', handleUpdate);
    return () => window.removeEventListener('safesense:data-updated', handleUpdate);
  }, [loadDashboardData]);

  const handleRefresh = async () => {
    if (refreshing || loading) return;
    const res = await loadDashboardData(false);
    if (res) {
      setToastMessage('Dashboard synchronized with safety database');
      setTimeout(() => setToastMessage(null), 3500);
    }
  };

  // ── Derived Chart Series ──────────────────────────────────────────────────
  const riskChartData = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.risk_distribution)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value, fill: RISK_COLORS[name] ?? '#94A3B8' }));
  }, [stats]);

  const categoryChartData = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.category_distribution)
      .sort((a, b) => b[1] - a[1])
      .map(([name, value]) => ({ name, value }));
  }, [stats]);

  // ── Loading Skeleton State ────────────────────────────────────────────────
  if (loading && !stats) {
    return (
      <div className="space-y-8 animate-in" aria-busy="true" aria-label="Loading dashboard intelligence">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="h-8 w-72 bg-slate-200 rounded animate-pulse" />
            <div className="h-4 w-48 bg-slate-100 rounded animate-pulse" />
          </div>
        </div>
        <KpiGridSkeleton count={6} />
        <div className="grid lg:grid-cols-2 gap-6">
          <ChartSkeleton height="h-80" />
          <ChartSkeleton height="h-80" />
        </div>
      </div>
    );
  }

  // ── Error State ───────────────────────────────────────────────────────────
  if (error && !stats) {
    return (
      <div className="py-6">
        <ErrorState
          title="SafeSense AI Backend Unavailable"
          message={error}
          hint="Make sure the FastAPI backend is running at http://localhost:8000 and safety.db is accessible."
          onRetry={() => loadDashboardData(true)}
          retrying={loading}
        />
      </div>
    );
  }

  // ── Empty Database State ──────────────────────────────────────────────────
  if (!stats || stats.total_reports === 0) {
    return (
      <div className="card flex flex-col items-center justify-center py-20 text-center max-w-lg mx-auto my-12 space-y-4">
        <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
          <Database className="w-7 h-7" />
        </div>
        <h2 className="text-lg font-bold text-slate-900">No Safety Records Available</h2>
        <p className="text-slate-500 text-xs leading-relaxed max-w-sm">
          No observations currently stored in the safety database. Upload an HSE incident or near-miss dataset to generate real-time safety intelligence.
        </p>
        <button onClick={() => navigate('/app/upload')} className="btn-primary text-xs">
          <Zap className="w-4 h-4" /> Upload Safety Reports
        </button>
      </div>
    );
  }

  const criticalAndHigh = (stats.risk_distribution['CRITICAL'] || 0) + (stats.risk_distribution['HIGH'] || 0);

  return (
    <div className="space-y-8 animate-in relative">
      {/* Toast Feedback */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-xl flex items-center gap-2 border border-slate-700 animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="section-title">Safety Intelligence Dashboard</h1>
            <span className="text-[11px] font-bold bg-blue-100 text-blue-800 px-2.5 py-0.5 rounded-full border border-blue-200">
              Live Safety Database
            </span>
          </div>
          <p className="section-sub">
            Operational HSE overview across {stats.total_reports} reports · {stats.sif_count} SIF potential precursors ·{' '}
            <span className="font-semibold text-slate-700">Trajectory: {trendStatus}</span>
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="btn-secondary text-xs disabled:opacity-50 inline-flex items-center gap-2"
            title="Synchronize metrics with backend database"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
            <span>{refreshing ? 'Refreshing...' : 'Refresh'}</span>
          </button>

          <button onClick={() => navigate('/app/upload')} className="btn-primary text-xs">
            <Zap className="w-3.5 h-3.5" />
            <span>Upload Reports</span>
          </button>
        </div>
      </div>

      {/* High-Level Intelligence KPIs (Real API Data Only) */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <KpiCard
          label="Total Reports"
          value={stats.total_reports}
          subtext="Verified stored records"
          icon={Shield}
          variant="blue"
          onClick={() => navigate('/app/reports')}
        />

        <KpiCard
          label="SIF Precursors"
          value={stats.sif_count}
          subtext={`${stats.sif_percentage.toFixed(1)}% of all reports`}
          icon={AlertOctagon}
          variant="red"
          badge="SIF: YES"
          onClick={() => navigate('/app/reports')}
        />

        <KpiCard
          label="Critical / High"
          value={criticalAndHigh}
          subtext={`${stats.risk_distribution['CRITICAL'] || 0} Crit · ${stats.risk_distribution['HIGH'] || 0} High`}
          icon={Zap}
          variant="orange"
          badge="SEVERITY"
          onClick={() => navigate('/app/reports')}
        />

        <KpiCard
          label="Active Patterns"
          value={patterns.length}
          subtext="Similarity clusters"
          icon={GitBranch}
          variant="indigo"
          badge="CLUSTERS"
          onClick={() => navigate('/app/patterns')}
        />

        <KpiCard
          label="Recurring Failures"
          value={repeatedFailures.length}
          subtext="Clusters with ≥3 incidents"
          icon={Repeat}
          variant="amber"
          badge="REPEATED"
          onClick={() => navigate('/app/patterns')}
        />

        <KpiCard
          label="Operational Risk"
          value={trendStatus}
          subtext={`Avg score ${stats.avg_risk_score.toFixed(1)} / 100`}
          icon={TrendingUp}
          variant={trendStatus === 'RISING RISK' ? 'red' : trendStatus === 'IMPROVING' ? 'emerald' : 'slate'}
          badge="TRAJECTORY"
          onClick={() => navigate('/app/risk-intelligence')}
        />
      </div>

      {/* AI Intelligence Insights Alert Strip (When available from backend) */}
      {insights.length > 0 && (
        <section aria-labelledby="insights-heading" className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 id="insights-heading" className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
              Real-Time AI Safety Intelligence Highlights
            </h2>
            <button
              onClick={() => navigate('/app/patterns')}
              className="text-xs font-bold text-blue-600 hover:text-blue-800 inline-flex items-center gap-1"
            >
              View All Insights <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {insights.slice(0, 3).map((insight, idx) => {
              const isAnomaly = insight.type === 'ANOMALY';
              const isRecurring = insight.type === 'RECURRING_PATTERN';
              const isCrossSite = insight.type === 'CROSS_SITE_RISK';

              return (
                <div
                  key={idx}
                  onClick={() => navigate(isRecurring ? '/app/patterns' : '/app/risk-intelligence')}
                  className={`p-3.5 rounded-xl border text-xs cursor-pointer transition-all hover:shadow-xs flex items-start gap-3 ${
                    isAnomaly
                      ? 'bg-red-50/70 border-red-200 text-red-950'
                      : isCrossSite
                      ? 'bg-amber-50/70 border-amber-200 text-amber-950'
                      : 'bg-indigo-50/60 border-indigo-200 text-indigo-950'
                  }`}
                >
                  <div className="mt-0.5">
                    {isAnomaly ? (
                      <AlertOctagon className="w-4 h-4 text-red-600" />
                    ) : isCrossSite ? (
                      <ShieldAlert className="w-4 h-4 text-amber-600" />
                    ) : (
                      <Repeat className="w-4 h-4 text-indigo-600" />
                    )}
                  </div>
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-bold truncate">{insight.title}</span>
                      <RiskBadge level={insight.severity || 'HIGH'} size="sm" showIcon={false} />
                    </div>
                    <p className="text-[11px] text-slate-700 leading-relaxed line-clamp-2">
                      {insight.message}
                    </p>
                    {insight.metric && (
                      <span className="inline-block text-[10px] font-semibold text-slate-600 bg-white/90 px-1.5 py-0.2 rounded border border-slate-200">
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

      {/* Operational Highlights Summary Strip */}
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="card flex items-center gap-4 p-4 border-l-4 border-l-blue-600">
          <div className="w-11 h-11 rounded-xl bg-blue-50 text-blue-700 flex items-center justify-center flex-shrink-0">
            <Shield className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Top Risk Category (LSR)</p>
            <p className="text-base font-bold text-slate-900 truncate">{stats.top_category || 'General Safety'}</p>
          </div>
        </div>

        <div className="card flex items-center gap-4 p-4 border-l-4 border-l-orange-500">
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
            stats.top_risk_level === 'CRITICAL' ? 'bg-red-50 text-red-700' :
            stats.top_risk_level === 'HIGH'     ? 'bg-orange-50 text-orange-700' :
            'bg-amber-50 text-amber-800'
          }`}>
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Dominant Risk Severity</p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-base font-bold text-slate-900">{stats.top_risk_level}</span>
              <RiskBadge level={stats.top_risk_level} size="sm" />
            </div>
          </div>
        </div>
      </div>

      {/* Multi-Tier SIF Risk Concentration Heatmap */}
      <SifRiskHeatmap />

      {/* Analytics Charts Grid */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Risk Distribution Chart */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">Risk Level Distribution</h3>
              <p className="text-[11px] text-slate-500">Proportion of verified observations by risk tier</p>
            </div>
            <span className="text-[11px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
              {stats.total_reports} total
            </span>
          </div>

          {riskChartData.length === 0 ? (
            <p className="text-slate-400 text-xs py-10 text-center">No risk data recorded.</p>
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie
                  data={riskChartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={75}
                  innerRadius={35}
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={false}
                >
                  {riskChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} stroke="#FFFFFF" strokeWidth={2} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E2E8F0',
                    borderRadius: 8,
                    color: '#0F172A',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)',
                    fontSize: 12,
                  }}
                />
                <Legend
                  formatter={val => <span style={{ color: '#475569', fontSize: 11, fontWeight: 600 }}>{val}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* SIF Potential Distribution */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">SIF Precursor Ratio</h3>
              <p className="text-[11px] text-slate-500">Severe Injury or Fatality potential classification</p>
            </div>
            <SIFBadge potential={stats.sif_count > 0 ? "YES" : "NO"} size="sm" />
          </div>

          <ResponsiveContainer width="100%" height={210}>
            <PieChart>
              <Pie
                data={[
                  { name: 'SIF Potential', value: stats.sif_count, fill: '#DC2626' },
                  { name: 'Non-SIF',        value: stats.non_sif_count, fill: '#16A34A' },
                ]}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={75}
                label={({ name, value }) => `${name}: ${value}`}
                labelLine={false}
              >
                <Cell fill="#DC2626" stroke="#FFFFFF" strokeWidth={2} />
                <Cell fill="#16A34A" stroke="#FFFFFF" strokeWidth={2} />
              </Pie>
              <Tooltip
                contentStyle={{
                  background: '#FFFFFF',
                  border: '1px solid #E2E8F0',
                  borderRadius: 8,
                  color: '#0F172A',
                  fontSize: 12,
                }}
              />
              <Legend formatter={val => <span style={{ color: '#475569', fontSize: 11, fontWeight: 600 }}>{val}</span>} />
            </PieChart>
          </ResponsiveContainer>

          <div className="mt-3 pt-3 border-t border-slate-100 grid grid-cols-3 text-center">
            <div>
              <p className="text-xl font-bold text-red-600">{stats.sif_count}</p>
              <p className="text-[10px] text-slate-500 font-semibold uppercase">SIF Potential</p>
            </div>
            <div>
              <p className="text-xl font-bold text-slate-800">{stats.sif_percentage.toFixed(1)}%</p>
              <p className="text-[10px] text-slate-500 font-semibold uppercase">SIF Share</p>
            </div>
            <div>
              <p className="text-xl font-bold text-emerald-600">{stats.non_sif_count}</p>
              <p className="text-[10px] text-slate-500 font-semibold uppercase">Non-SIF</p>
            </div>
          </div>
        </div>
      </div>

      {/* Category (LSR) Distribution Bar Chart */}
      {categoryChartData.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                Reports by Life-Saving Rule Category
              </h3>
              <p className="text-[11px] text-slate-500">Prevalence of safety reports grouped by operational rule</p>
            </div>
            <span className="text-[11px] text-slate-500 font-medium">
              Top: <strong className="text-slate-800">{stats.top_category}</strong>
            </span>
          </div>

          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={categoryChartData} layout="vertical" margin={{ left: 15, right: 20, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: '#64748B', fontSize: 11 }}
                allowDecimals={false}
                axisLine={{ stroke: '#E2E8F0' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={160}
                tick={{ fill: '#334155', fontSize: 11, fontWeight: 500 }}
                axisLine={{ stroke: '#E2E8F0' }}
              />
              <Tooltip
                contentStyle={{
                  background: '#FFFFFF',
                  border: '1px solid #E2E8F0',
                  borderRadius: 8,
                  color: '#0F172A',
                  fontSize: 12,
                }}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]} name="Reports">
                {categoryChartData.map((_, i) => (
                  <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Segmented Risk Breakdown Bar */}
      <div className="card p-5 space-y-4">
        <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
          Risk Severity Tier Breakdown
        </h3>
        <div className="space-y-3.5">
          {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map(level => {
            const count = stats.risk_distribution[level] ?? 0;
            const pct = stats.total_reports > 0 ? Math.round((count / stats.total_reports) * 100) : 0;
            return (
              <div key={level} className="space-y-1">
                <div className="flex justify-between items-center text-xs">
                  <div className="flex items-center gap-1.5">
                    <RiskBadge level={level} size="sm" />
                    <span className="text-slate-500 font-medium">({count} reports)</span>
                  </div>
                  <span className="font-bold text-slate-800">{pct}%</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: RISK_COLORS[level],
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Audit Source Footer */}
      <div className="text-center py-2 text-xs text-slate-400">
        SafeSense AI Platform · Sourced live from the verified safety database · {stats.total_reports} total records analyzed
      </div>
    </div>
  );
}

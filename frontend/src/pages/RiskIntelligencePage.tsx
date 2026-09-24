/**
 * RiskIntelligencePage.tsx — SafeSense AI Risk Intelligence & Operational Trajectory
 *
 * Sourced directly from backend endpoints:
 * - GET /api/reports (stored observations)
 * - GET /api/risk-intelligence/trends (monthly time-series, trajectory & statistical anomalies)
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend
} from 'recharts';
import {
  AlertTriangle, TrendingUp, TrendingDown, Minus, Activity, RefreshCw,
  Database, ShieldAlert, Sparkles, AlertOctagon, MapPin, Calendar, Info
} from 'lucide-react';

import EmptyState from '../components/EmptyState';
import ErrorState from '../components/ErrorState';
import { RiskBadge, SIFBadge } from '../components/RiskBadge';
import KpiCard from '../components/KpiCard';

import {
  fetchReports,
  fetchTrendsIntelligence,
  ApiReport,
  TrendPoint,
  PatternAnomaly,
  AIInsight,
} from '../services/api';

import { computeBarrierFailures, detectBarrierFailure } from '../utils/riskEngine';
import { SafetyReport, RiskLevel, SIFPotential } from '../types';

export default function RiskIntelligencePage() {
  const [reports, setReports] = useState<ApiReport[]>([]);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [anomalies, setAnomalies] = useState<PatternAnomaly[]>([]);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [trendStatus, setTrendStatus] = useState<string>('STABLE');
  const [trendReason, setTrendReason] = useState<string>('');

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToast, setRefreshToast] = useState(false);

  // ── Fetch Data ────────────────────────────────────────────────────────────
  const loadReports = useCallback(async (isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const [reportsRes, trendsRes] = await Promise.all([
        fetchReports(),
        fetchTrendsIntelligence().catch(() => ({
          data: [],
          trend: 'STABLE',
          trend_reason: 'Trend calculation available with historical time-series.',
          anomalies: [],
          insights: [],
        })),
      ]);

      const rawList: ApiReport[] =
        (reportsRes as any).reports ||
        (reportsRes as any).data ||
        (Array.isArray(reportsRes) ? reportsRes : []);

      setReports(rawList);
      setTrends(trendsRes.data || []);
      setTrendStatus(trendsRes.trend || 'STABLE');
      setTrendReason(trendsRes.trend_reason || '');
      setAnomalies(trendsRes.anomalies || []);
      setInsights(trendsRes.insights || []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch safety intelligence data';
      setError(msg);
      if (isInitial) {
        setReports([]);
        setTrends([]);
        setAnomalies([]);
        setInsights([]);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadReports(true);
  }, [loadReports]);

  // Listen for global data updates
  useEffect(() => {
    const handleUpdate = () => loadReports(false);
    window.addEventListener('safesense:data-updated', handleUpdate);
    return () => window.removeEventListener('safesense:data-updated', handleUpdate);
  }, [loadReports]);

  const handleRefresh = async () => {
    await loadReports(false);
    setRefreshToast(true);
    setTimeout(() => setRefreshToast(false), 3000);
  };

  // ── Mapped Reports Schema ─────────────────────────────────────────────────
  const mappedReports: SafetyReport[] = useMemo(() => {
    return reports.map(r => {
      const repId = r.report_id || String(r.id || '');
      const dateStr = r.date || (r.created_at ? r.created_at.slice(0, 10) : undefined);
      return {
        id: repId,
        report_id: repId.startsWith('RPT-') ? repId : `RPT-${repId.slice(0, 6)}`,
        report_text: r.description || '',
        risk_level: (r.risk_level?.toUpperCase() as RiskLevel) || 'LOW',
        risk_score: r.risk_score || 0,
        sif_potential: (r.sif_potential?.toUpperCase() as SIFPotential) || 'NO',
        life_saving_rule: r.category || 'General Safety',
        barrier_failure: detectBarrierFailure(r.description || ''),
        date: dateStr,
        report_type: 'Safety Observation',
      };
    });
  }, [reports]);

  // Failed barrier frequencies
  const barriers = useMemo(() => computeBarrierFailures(mappedReports), [mappedReports]);

  // Monthly trend: Use backend SQLite aggregation
  const monthlyData = useMemo(() => {
    if (trends && trends.length > 0) return trends;

    // Fallback if trends API returned empty array
    const monthly: Record<string, { month: string; total: number; sif: number; critical: number }> = {};
    for (const r of mappedReports) {
      if (!r.date) continue;
      const month = r.date.slice(0, 7);
      if (!monthly[month]) monthly[month] = { month, total: 0, sif: 0, critical: 0 };
      monthly[month].total++;
      if (r.sif_potential === 'YES') monthly[month].sif++;
      if (r.risk_level === 'CRITICAL') monthly[month].critical++;
    }
    return Object.values(monthly).sort((a, b) => a.month.localeCompare(b.month));
  }, [trends, mappedReports]);

  // Life-Saving Rule distribution
  const lsrData = useMemo(() => {
    const counts: Record<string, { name: string; total: number; sif: number }> = {};
    for (const r of mappedReports) {
      const rule = r.life_saving_rule || 'General Safety';
      if (!counts[rule]) counts[rule] = { name: rule, total: 0, sif: 0 };
      counts[rule].total++;
      if (r.sif_potential === 'YES') counts[rule].sif++;
    }
    return Object.values(counts).sort((a, b) => b.total - a.total).slice(0, 8);
  }, [mappedReports]);

  // Underlying time period
  const periodRange = useMemo(() => {
    if (monthlyData.length === 0) return null;
    const first = monthlyData[0].month;
    const last = monthlyData[monthlyData.length - 1].month;
    return first === last ? first : `${first} — ${last}`;
  }, [monthlyData]);

  // Aggregate metrics
  const sifCount = useMemo(() => {
    return reports.filter(r => String(r.sif_potential).toUpperCase() === 'YES').length;
  }, [reports]);

  const criticalCount = useMemo(() => {
    return reports.filter(r => String(r.risk_level).toUpperCase() === 'CRITICAL').length;
  }, [reports]);

  // ── Loading State ─────────────────────────────────────────────────────────
  if (loading && reports.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-28 space-y-4">
        <span className="w-8 h-8 border-3 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
        <p className="text-sm font-semibold text-slate-700">Loading Risk Intelligence &amp; Trajectory...</p>
      </div>
    );
  }

  // ── Error State ───────────────────────────────────────────────────────────
  if (error && reports.length === 0) {
    return (
      <div className="py-8">
        <ErrorState
          title="Failed to Load Risk Intelligence"
          message={error}
          hint="Make sure the backend is running and the database has valid report records."
          onRetry={() => loadReports(true)}
          retrying={loading}
        />
      </div>
    );
  }

  // ── Empty State ───────────────────────────────────────────────────────────
  if (!loading && reports.length === 0) {
    return (
      <EmptyState
        title="No Safety Data Available"
        message="Upload an incident dataset to generate trajectory analysis, statistical anomaly spikes, and barrier breakdown."
      />
    );
  }

  return (
    <div className="space-y-8 animate-in relative">
      {/* Toast Notification */}
      {refreshToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-xl flex items-center gap-2 border border-slate-700 animate-in fade-in slide-in-from-bottom-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <span>Risk Intelligence refreshed with latest records</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="section-title">Risk Intelligence &amp; Trajectory</h1>
            {periodRange && (
              <span className="bg-slate-100 text-slate-700 border border-slate-200 text-xs font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1.5">
                <Calendar className="w-3 h-3 text-slate-500" />
                {periodRange}
              </span>
            )}
          </div>
          <p className="section-sub">
            Historical trajectory, statistical anomaly detection, and barrier failure intelligence across {reports.length} safety reports.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg font-medium border border-slate-200 shadow-2xs flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-blue-600" />
            <span>{reports.length} Records Analyzed</span>
          </div>

          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="btn-secondary text-xs py-1.5 px-3"
            title="Refresh analytics from SQLite database"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-blue-600' : ''}`} />
            <span>{refreshing ? 'Refreshing...' : 'Refresh'}</span>
          </button>
        </div>
      </div>

      {/* KPI Cards Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Total Reports"
          value={reports.length}
          subtext="Stored in SQLite"
          icon={Database}
          variant="blue"
        />

        <KpiCard
          label="SIF Precursors"
          value={sifCount}
          subtext={`${((sifCount / (reports.length || 1)) * 100).toFixed(1)}% of dataset`}
          icon={AlertOctagon}
          variant="red"
          badge="SIF: YES"
        />

        <KpiCard
          label="Critical Severity"
          value={criticalCount}
          subtext="Highest priority incidents"
          icon={AlertTriangle}
          variant="orange"
          badge="CRITICAL"
        />

        <KpiCard
          label="Statistical Trajectory"
          value={trendStatus}
          subtext={periodRange ? `Period: ${periodRange}` : 'Overall trajectory'}
          icon={trendStatus === 'RISING RISK' ? TrendingUp : trendStatus === 'IMPROVING' ? TrendingDown : Minus}
          variant={trendStatus === 'RISING RISK' ? 'red' : trendStatus === 'IMPROVING' ? 'emerald' : 'slate'}
          badge="TRAJECTORY"
        />
      </div>

      {/* ── Statistical Anomaly Spikes Section (Real Backend Spikes) ─────────── */}
      <section aria-labelledby="anomalies-heading" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertOctagon className="w-4 h-4 text-red-600" />
            <h2 id="anomalies-heading" className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Statistical Anomaly Spikes ({anomalies.length})
            </h2>
          </div>
          <span className="text-[11px] text-slate-500 font-medium">
            Threshold: &gt;= 1.5x baseline volume
          </span>
        </div>

        {anomalies.length === 0 ? (
          <div className="card p-4 text-xs text-slate-600 bg-slate-50 border-slate-200 flex items-center gap-2">
            <Info className="w-4 h-4 text-slate-400 shrink-0" />
            <span>No statistical anomaly spikes (≥1.5x baseline) detected across current temporal series or operating facilities.</span>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-4">
            {anomalies.map((anomaly, idx) => (
              <div
                key={idx}
                className="card border-red-200 bg-red-50/60 p-4 flex items-start gap-3.5 shadow-2xs"
              >
                <div className="w-9 h-9 rounded-lg bg-red-100 text-red-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <AlertOctagon className="w-4 h-4" />
                </div>

                <div className="space-y-1 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-bold text-red-950 uppercase tracking-wider">
                      {anomaly.type === 'TEMPORAL_SPIKE' ? 'Temporal Volume Spike' : 'Site Concentration Spike'}
                    </span>
                    <span className="text-[11px] font-bold bg-red-100 text-red-800 border border-red-300 px-2 py-0.5 rounded-full">
                      {anomaly.ratio ? `${anomaly.ratio}x Baseline` : 'Spike'}
                    </span>
                  </div>

                  <p className="text-xs font-bold text-slate-900">
                    Location: {anomaly.site || 'Global Operations'}
                  </p>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {anomaly.reason}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Monthly Safety Trend Trajectory ─────────────────────────────────── */}
      {monthlyData.length > 0 ? (
        <section aria-labelledby="trend-heading" className="space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-blue-600" />
              <h2 id="trend-heading" className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                Monthly Safety Trajectory ({periodRange || 'Historical'})
              </h2>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`text-xs font-bold px-2.5 py-1 rounded-md border flex items-center gap-1.5 ${
                  trendStatus === 'RISING RISK'
                    ? 'bg-red-50 text-red-800 border-red-300'
                    : trendStatus === 'IMPROVING'
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                    : 'bg-slate-100 text-slate-800 border-slate-300'
                }`}
              >
                {trendStatus === 'RISING RISK' ? (
                  <TrendingUp className="w-3.5 h-3.5 text-red-600" />
                ) : trendStatus === 'IMPROVING' ? (
                  <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
                ) : (
                  <Minus className="w-3.5 h-3.5 text-slate-600" />
                )}
                Trajectory: {trendStatus}
              </span>
            </div>
          </div>

          {trendReason && (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
              <div className="leading-relaxed">
                <strong className="text-slate-900 font-bold">Pattern Engine Trend Assessment: </strong>
                <span>{trendReason}</span>
              </div>
            </div>
          )}

          <div className="card p-5">
            <ResponsiveContainer width="100%" height={270}>
              <LineChart data={monthlyData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="month" tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} />
                <YAxis tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E2E8F0',
                    borderRadius: 8,
                    color: '#0F172A',
                    fontSize: 12,
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)',
                  }}
                />
                <Legend formatter={v => <span style={{ color: '#475569', fontSize: 11, fontWeight: 600 }}>{v}</span>} />
                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="#2563EB"
                  name="Total Reports"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#2563EB' }}
                />
                <Line
                  type="monotone"
                  dataKey="sif"
                  stroke="#DC2626"
                  name="SIF Potential"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#DC2626' }}
                />
                <Line
                  type="monotone"
                  dataKey="critical"
                  stroke="#EA580C"
                  name="Critical Severity"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={{ r: 3.5, fill: '#EA580C' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      ) : (
        <div className="card p-5 text-slate-500 text-xs flex items-center gap-2 bg-slate-50">
          <Activity className="w-4 h-4 text-slate-400" />
          <span>Timeline trajectory will populate once date-indexed safety records are saved.</span>
        </div>
      )}

      {/* ── LSR Distribution & Barrier Failures ─────────────────────────────── */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* LSR Distribution */}
        <section aria-labelledby="lsr-dist-heading" className="space-y-3">
          <h2 id="lsr-dist-heading" className="text-xs font-bold text-slate-800 uppercase tracking-wider">
            Life-Saving Rule Risk Distribution
          </h2>
          <div className="card p-5">
            {lsrData.length === 0 ? (
              <p className="text-xs text-slate-500 py-10 text-center">No categories identified.</p>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={lsrData} layout="vertical" margin={{ left: 15, right: 20, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
                  <XAxis type="number" tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={150}
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
                  <Legend formatter={v => <span style={{ color: '#475569', fontSize: 11, fontWeight: 600 }}>{v}</span>} />
                  <Bar dataKey="total" fill="#2563EB" name="Total Reports" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="sif" fill="#DC2626" name="SIF Precursors" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

        {/* Failed Safety Barriers */}
        <section aria-labelledby="barriers-heading" className="space-y-3">
          <h2 id="barriers-heading" className="text-xs font-bold text-slate-800 uppercase tracking-wider">
            Failed Safety Barriers (Empirical Recurrence)
          </h2>
          <div className="card p-5">
            {barriers.length === 0 ? (
              <p className="text-xs text-slate-500 py-10 text-center">No barrier failures recorded.</p>
            ) : (
              <div className="space-y-3.5">
                {barriers.slice(0, 8).map(b => (
                  <div key={b.barrier}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-800 font-bold truncate flex-1 mr-2">{b.barrier}</span>
                      <span className="text-slate-500 flex-shrink-0 font-semibold">
                        {b.count} reports ({b.percentage}%)
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-red-600 transition-all duration-700"
                        style={{ width: `${b.percentage}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Causation vs Correlation Note */}
      <div className="card p-4 bg-slate-50/80 border-slate-200 text-xs text-slate-600 flex items-start gap-2.5">
        <Info className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <strong className="text-slate-800">Operational Decision Support Disclaimer: </strong>
          Risk Intelligence distributions, trend trajectories, and anomaly spikes reflect empirical incident logs and statistical correlations. SafeSense AI provides prioritized precursor visibility for HSE officers and does not assert definitive root causes without formal on-site incident investigations.
        </div>
      </div>
    </div>
  );
}

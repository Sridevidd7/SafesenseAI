import { useState, useEffect, useMemo, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, Legend } from 'recharts';
import { AlertTriangle, TrendingUp, Activity, RefreshCw, Database, ShieldAlert, Sparkles } from 'lucide-react';
import EmptyState from '../components/EmptyState';
import { fetchReports, fetchRiskIntelligenceTrends, ApiReport, TrendPoint } from '../services/api';
import { computeEarlyWarnings, computeBarrierFailures, detectBarrierFailure } from '../utils/riskEngine';
import { SafetyReport, RiskLevel, SIFPotential } from '../types';

export default function RiskIntelligencePage() {
  const [reports, setReports] = useState<ApiReport[]>([]);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToast, setRefreshToast] = useState(false);

  // ─── Fetch reports and trends from backend API ──────────────────────────────
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
        fetchRiskIntelligenceTrends().catch(() => [] as TrendPoint[]),
      ]);

      const rawList: ApiReport[] =
        (reportsRes as any).reports ||
        (reportsRes as any).data ||
        (Array.isArray(reportsRes) ? reportsRes : []);

      setReports(rawList);
      setTrends(trendsRes || []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch safety intelligence data';
      console.error('Risk Intelligence fetch error:', err);
      setError(msg);
      if (isInitial) {
        setReports([]);
        setTrends([]);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadReports(true);
  }, [loadReports]);

  // Listen for global data updates (e.g. after CSV upload or reset)
  useEffect(() => {
    const handleUpdate = () => {
      loadReports(false);
    };
    window.addEventListener('safesense:data-updated', handleUpdate);
    return () => window.removeEventListener('safesense:data-updated', handleUpdate);
  }, [loadReports]);

  // ─── Refresh Button Handler ────────────────────────────────────────────────
  const handleRefresh = async () => {
    await loadReports(false);
    setRefreshToast(true);
    setTimeout(() => setRefreshToast(false), 3000);
  };

  // ─── Map API reports to SafetyReport schema ─────────────────────────────────
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

  // ─── Computed Intelligence Metrics ──────────────────────────────────────────
  const warnings = useMemo(() => computeEarlyWarnings(mappedReports), [mappedReports]);
  const barriers = useMemo(() => computeBarrierFailures(mappedReports), [mappedReports]);

  // Monthly trend: Prefer backend SQLite aggregation, fallback to mapped reports
  const monthlyData = useMemo(() => {
    if (trends && trends.length > 0) {
      return trends;
    }
    const monthly: Record<string, { month: string; total: number; sif: number; critical: number }> = {};
    for (const r of mappedReports) {
      if (!r.date) continue;
      const month = r.date.slice(0, 7);
      if (!monthly[month]) monthly[month] = { month, total: 0, sif: 0, critical: 0 };
      monthly[month].total++;
      if (r.sif_potential === 'YES') monthly[month].sif++;
      if (r.risk_level === 'CRITICAL') {
        monthly[month].critical++;
      }
    }
    return Object.values(monthly).sort((a, b) => a.month.localeCompare(b.month));
  }, [trends, mappedReports]);

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

  // ─── Loading State ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-28 space-y-4">
        <span className="w-8 h-8 border-3 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
        <p className="text-sm font-semibold text-slate-600">Loading Risk Intelligence metrics...</p>
      </div>
    );
  }

  // ─── Error State ───────────────────────────────────────────────────────────
  if (error && reports.length === 0) {
    return (
      <div className="card border-red-200 bg-red-50/50 p-8 text-center max-w-lg mx-auto my-12 space-y-4">
        <ShieldAlert className="w-12 h-12 text-red-500 mx-auto" />
        <h3 className="text-lg font-bold text-slate-900">Failed to Load Risk Intelligence</h3>
        <p className="text-xs text-red-700">{error}</p>
        <button onClick={() => loadReports(true)} className="btn-primary mx-auto text-xs">
          <RefreshCw className="w-3.5 h-3.5" /> Retry
        </button>
      </div>
    );
  }

  // ─── Empty State ───────────────────────────────────────────────────────────
  if (!loading && (!reports || reports.length === 0)) {
    return (
      <EmptyState
        title="No Safety Data Available"
        message="Upload a dataset to generate early warnings, barrier failure analytics, and risk trend metrics."
      />
    );
  }

  return (
    <div className="space-y-8 animate-in">
      {/* Toast notification */}
      {refreshToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-xl flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          Risk Intelligence updated with latest database records
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="section-title">Risk Intelligence</h1>
          <p className="section-sub">
            Early warnings, barrier failure analysis, and risk trends derived from {reports.length} stored safety reports.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-xs text-slate-500 bg-slate-100 px-3 py-1.5 rounded-lg font-medium border border-slate-200 flex items-center gap-1.5">
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
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* ─── Early Warnings Section ────────────────────────────────────────── */}
      <section>
        <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600" /> Early Warning Center
        </h2>
        {warnings.length === 0 ? (
          <div className="card text-slate-600 text-sm bg-slate-50/60 border-slate-200">
            No critical risk concentrations or recurring precursor thresholds exceeded in the current dataset.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-4">
            {warnings.map(w => (
              <div
                key={w.id}
                className={`card border p-5 ${
                  w.type === 'CRITICAL'
                    ? 'border-red-200 bg-red-50/40'
                    : w.type === 'WARNING'
                    ? 'border-orange-200 bg-orange-50/40'
                    : 'border-amber-200 bg-amber-50/40'
                }`}
              >
                <div className="flex items-start gap-3.5">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      w.type === 'CRITICAL'
                        ? 'bg-red-100 text-red-700'
                        : w.type === 'WARNING'
                        ? 'bg-orange-100 text-orange-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`text-xs font-bold uppercase tracking-wider ${
                          w.type === 'CRITICAL'
                            ? 'text-red-700'
                            : w.type === 'WARNING'
                            ? 'text-orange-700'
                            : 'text-amber-700'
                        }`}
                      >
                        {w.type}
                      </span>
                    </div>
                    <p className="font-bold text-slate-900 text-sm">{w.title}</p>
                    <p className="text-slate-600 text-xs mt-1 leading-relaxed">{w.description}</p>
                    {w.affected_sites && w.affected_sites.length > 0 && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {w.affected_sites.slice(0, 3).map(site => (
                          <span
                            key={site}
                            className="text-xs bg-white text-slate-700 border border-slate-200 px-2.5 py-0.5 rounded-md shadow-2xs font-medium"
                          >
                            {site}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="text-lg font-bold text-red-600">+{w.change_pct}%</div>
                    <div className="text-xs text-slate-500 font-medium">vs baseline</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ─── Monthly Safety Trend ──────────────────────────────────────────── */}
      {monthlyData.length > 0 ? (
        <section>
          <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-600" /> Monthly Safety Trend
          </h2>
          <div className="card">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="month" tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} />
                <YAxis tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} />
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E2E8F0',
                    borderRadius: 8,
                    color: '#0F172A',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)',
                  }}
                />
                <Legend formatter={v => <span style={{ color: '#475569', fontSize: 12 }}>{v}</span>} />
                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="#3B82F6"
                  name="Total Reports"
                  strokeWidth={2.5}
                  dot={{ r: 3.5, fill: '#3B82F6' }}
                />
                <Line
                  type="monotone"
                  dataKey="sif"
                  stroke="#EF4444"
                  name="SIF Potential"
                  strokeWidth={2.5}
                  dot={{ r: 3.5, fill: '#EF4444' }}
                />
                <Line
                  type="monotone"
                  dataKey="critical"
                  stroke="#F97316"
                  name="Critical Severity"
                  strokeWidth={2.5}
                  dot={{ r: 3.5, fill: '#F97316' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      ) : (
        <div className="card text-slate-500 text-sm flex items-center gap-2 bg-slate-50">
          <Activity className="w-4 h-4 text-slate-400" />
          Trend analysis timeline will appear once date-indexed records are stored.
        </div>
      )}

      {/* ─── LSR Distribution & Barrier Failures ───────────────────────────── */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* LSR Distribution */}
        <section>
          <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
            Life-Saving Rule Distribution
          </h2>
          <div className="card">
            {lsrData.length === 0 ? (
              <p className="text-xs text-slate-500 py-10 text-center">No categories identified.</p>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={lsrData} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
                  <XAxis type="number" tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={140}
                    tick={{ fill: '#334155', fontSize: 11 }}
                    axisLine={{ stroke: '#E2E8F0' }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#FFFFFF',
                      border: '1px solid #E2E8F0',
                      borderRadius: 8,
                      color: '#0F172A',
                      boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)',
                    }}
                  />
                  <Legend formatter={v => <span style={{ color: '#475569', fontSize: 12 }}>{v}</span>} />
                  <Bar dataKey="total" fill="#3B82F6" name="Total Reports" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="sif" fill="#EF4444" name="SIF Potential" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

        {/* Barrier Failures */}
        <section>
          <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
            Failed Safety Barriers
          </h2>
          <div className="card">
            {barriers.length === 0 ? (
              <p className="text-xs text-slate-500 py-10 text-center">No barrier failures recorded.</p>
            ) : (
              <div className="space-y-3.5">
                {barriers.slice(0, 8).map(b => (
                  <div key={b.barrier}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-800 font-medium truncate flex-1 mr-2">{b.barrier}</span>
                      <span className="text-slate-500 flex-shrink-0 font-medium">
                        {b.count} ({b.percentage}%)
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-red-500 transition-all duration-700"
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
    </div>
  );
}

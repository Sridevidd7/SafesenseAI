/**
 * DashboardPage.tsx
 *
 * Data source: GET /api/dashboard/stats  (live from SQLite DB)
 * No hardcoded values. No demo data. Every metric comes from the backend.
 * Clean, modern light theme.
 */
import { useMemo, useState } from 'react';
import { useDashboardStats } from '../hooks/useDashboardStats';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  AlertTriangle, TrendingUp, Shield, Activity, Zap, RefreshCw, Database, CheckCircle,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

// ─── Colour maps ──────────────────────────────────────────────────────────────
const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#EF4444',
  HIGH:     '#F97316',
  MEDIUM:   '#F59E0B',
  LOW:      '#22C55E',
};

const CATEGORY_COLORS = [
  '#3B82F6', '#8B5CF6', '#F59E0B', '#EF4444',
  '#22C55E', '#06B6D4', '#F97316', '#A855F7',
];

// ─── Skeleton loader ──────────────────────────────────────────────────────────
function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-slate-200 rounded-lg ${className}`} />
  );
}

// ─── Empty state when DB has no reports ──────────────────────────────────────
function NoDataState() {
  const navigate = useNavigate();
  return (
    <div className="card flex flex-col items-center justify-center py-24 text-center">
      <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center mb-4">
        <Database className="w-7 h-7 text-slate-400" />
      </div>
      <h2 className="text-xl font-bold text-slate-900 mb-2">No data available</h2>
      <p className="text-slate-500 text-sm mb-6 max-w-sm">
        Upload a CSV file to start seeing live dashboard analytics from the backend.
      </p>
      <button onClick={() => navigate('/upload')} className="btn-primary">
        <Zap className="w-4 h-4" />
        Upload Reports
      </button>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const navigate = useNavigate();
  const { stats, loading, refreshing, error, refresh } = useDashboardStats();
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const handleRefresh = async () => {
    if (refreshing || loading) return;
    const result = await refresh();
    if (result) {
      setToastMessage('Dashboard updated with latest data');
      setTimeout(() => setToastMessage(null), 3000);
    }
  };

  // ── Derived chart data (computed from live API response) ──────────────────
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

  // ── Loading skeleton ──────────────────────────────────────────────────────
  if (loading && !stats) {
    return (
      <div className="space-y-8 animate-in">
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-8 w-64 mb-2" />
            <Skeleton className="h-4 w-48" />
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <div className="grid lg:grid-cols-2 gap-6">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="animate-in">
        <div className="bg-red-50 border border-red-200 rounded-xl p-5 flex items-start gap-4 text-red-900 shadow-sm">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-semibold text-red-900 mb-1">Backend unavailable</h3>
            <p className="text-red-700 text-sm mb-3">{error}</p>
            <p className="text-red-600 text-xs mb-3">
              Make sure the FastAPI backend is running on port 8000.
            </p>
            <button onClick={handleRefresh} disabled={refreshing || loading} className="btn-secondary text-sm bg-white hover:bg-red-50 text-red-900 border-red-200 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2">
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Retrying...' : 'Retry'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Empty DB ──────────────────────────────────────────────────────────────
  if (!stats || stats.total_reports === 0) {
    return (
      <div className="animate-in">
        <NoDataState />
      </div>
    );
  }

  // ── KPI cards ─────────────────────────────────────────────────────────────
  const sifPct = stats.sif_percentage.toFixed(1);
  const KPIS = [
    {
      label: 'Total Reports',
      value: stats.total_reports,
      icon: Shield,
      accentBorder: 'border-l-blue-600',
      iconColor: 'text-blue-600',
      iconBg: 'bg-blue-50',
      sub: 'All stored reports',
    },
    {
      label: 'SIF Potential',
      value: stats.sif_count,
      icon: AlertTriangle,
      accentBorder: 'border-l-red-500',
      iconColor: 'text-red-600',
      iconBg: 'bg-red-50',
      sub: `${sifPct}% of total`,
    },
    {
      label: 'Critical Priority',
      value: stats.risk_distribution['CRITICAL'] ?? 0,
      icon: Zap,
      accentBorder: 'border-l-red-600',
      iconColor: 'text-red-600',
      iconBg: 'bg-red-50',
      sub: 'Highest priority',
    },
    {
      label: 'High Risk',
      value: stats.risk_distribution['HIGH'] ?? 0,
      icon: TrendingUp,
      accentBorder: 'border-l-orange-500',
      iconColor: 'text-orange-600',
      iconBg: 'bg-orange-50',
      sub: 'Requires attention',
    },
    {
      label: 'Avg Risk Score',
      value: stats.avg_risk_score.toFixed(1),
      icon: Activity,
      accentBorder: 'border-l-indigo-600',
      iconColor: 'text-indigo-600',
      iconBg: 'bg-indigo-50',
      sub: 'Out of 100',
    },
  ];

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-8 animate-in relative">

      {/* Floating toast notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white text-xs font-medium px-4 py-2.5 rounded-lg shadow-xl flex items-center gap-2 border border-slate-700 animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="section-title">Safety Intelligence Dashboard</h1>
          <p className="section-sub">
            {stats.total_reports} reports in database ·{' '}
            {stats.sif_count} SIF potential ·{' '}
            <span className="text-slate-500 font-medium">Live data from backend</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
            title="Fetch latest data from backend APIs"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          <button onClick={() => navigate('/upload')} className="btn-primary text-sm">
            <Zap className="w-4 h-4" />
            Upload Reports
          </button>
        </div>
      </div>


      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
        {KPIS.map(kpi => (
          <div
            key={kpi.label}
            className={`card border-l-4 ${kpi.accentBorder} flex flex-col justify-between`}
          >
            <div className="flex items-start justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{kpi.label}</span>
              <div className={`w-7 h-7 rounded-md ${kpi.iconBg} ${kpi.iconColor} flex items-center justify-center`}>
                <kpi.icon className="w-4 h-4" />
              </div>
            </div>
            <div>
              <div className="text-3xl font-bold text-slate-900 mb-1">{kpi.value}</div>
              <div className="text-xs text-slate-500 font-normal">{kpi.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Highlights row */}
      <div className="grid sm:grid-cols-2 gap-5">
        <div className="card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 mb-0.5">Top Risk Category</p>
            <p className="text-base font-bold text-slate-900">{stats.top_category}</p>
          </div>
        </div>
        <div className="card flex items-center gap-4">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${
            stats.top_risk_level === 'CRITICAL' ? 'bg-red-50 text-red-600' :
            stats.top_risk_level === 'HIGH'     ? 'bg-orange-50 text-orange-600' :
            'bg-amber-50 text-amber-600'
          }`}>
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 mb-0.5">Dominant Risk Level</p>
            <p className="text-base font-bold text-slate-900">{stats.top_risk_level}</p>
          </div>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid lg:grid-cols-2 gap-6">

        {/* Risk Distribution Pie */}
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Risk Level Distribution</h3>
          {riskChartData.length === 0 ? (
            <p className="text-slate-400 text-sm">No risk data available.</p>
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie
                  data={riskChartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={false}
                >
                  {riskChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: '#FFFFFF',
                    border: '1px solid #E2E8F0',
                    borderRadius: 8,
                    color: '#0F172A',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)',
                  }}
                />
                <Legend
                  formatter={val => (
                    <span style={{ color: '#475569', fontSize: 12 }}>{val}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* SIF Potential Pie */}
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">SIF Potential Distribution</h3>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie
                data={[
                  { name: 'SIF Potential', value: stats.sif_count,     fill: '#EF4444' },
                  { name: 'No SIF',        value: stats.non_sif_count, fill: '#22C55E' },
                ]}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                label={({ name, value }) => `${name}: ${value}`}
                labelLine={false}
              >
                <Cell fill="#EF4444" />
                <Cell fill="#22C55E" />
              </Pie>
              <Tooltip
                contentStyle={{
                  background: '#FFFFFF',
                  border: '1px solid #E2E8F0',
                  borderRadius: 8,
                  color: '#0F172A',
                  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)',
                }}
              />
              <Legend
                formatter={val => (
                  <span style={{ color: '#475569', fontSize: 12 }}>{val}</span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-4 pt-4 border-t border-slate-100 flex justify-around text-center">
            <div>
              <p className="text-2xl font-bold text-red-600">{stats.sif_count}</p>
              <p className="text-xs text-slate-500 font-medium">SIF Potential</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-700">{sifPct}%</p>
              <p className="text-xs text-slate-500 font-medium">of total</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-green-600">{stats.non_sif_count}</p>
              <p className="text-xs text-slate-500 font-medium">No SIF</p>
            </div>
          </div>
        </div>

      </div>

      {/* Category distribution bar chart */}
      {categoryChartData.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">
            Reports by Category (Life-Saving Rule)
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={categoryChartData}
              layout="vertical"
              margin={{ left: 10, right: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: '#64748B', fontSize: 11 }}
                allowDecimals={false}
                axisLine={{ stroke: '#E2E8F0' }}
                tickLine={{ stroke: '#E2E8F0' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={170}
                tick={{ fill: '#334155', fontSize: 11 }}
                axisLine={{ stroke: '#E2E8F0' }}
                tickLine={{ stroke: '#E2E8F0' }}
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
              <Bar dataKey="value" radius={[0, 4, 4, 0]} name="Reports">
                {categoryChartData.map((_, i) => (
                  <Cell
                    key={i}
                    fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Risk level breakdown */}
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-900 mb-4">Risk Level Breakdown</h3>
        <div className="space-y-4">
          {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map(level => {
            const count = stats.risk_distribution[level] ?? 0;
            const pct   = stats.total_reports > 0
              ? Math.round((count / stats.total_reports) * 100)
              : 0;
            return (
              <div key={level}>
                <div className="flex justify-between text-xs mb-1.5">
                  <span
                    className="font-semibold"
                    style={{ color: RISK_COLORS[level] }}
                  >
                    {level}
                  </span>
                  <span className="text-slate-600 font-medium">{count} reports ({pct}%)</span>
                </div>
                <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
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

      {/* Footer note */}
      <div className="text-center py-2">
        <p className="text-xs text-slate-400">
          All data sourced live from the SafeSense AI backend database ·
          {' '}{stats.total_reports} reports total
        </p>
      </div>

    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { RiskBadge } from '../components/RiskBadge';
import {
  fetchCommandCenterData,
  fetchAnalyticsSites,
  fetchAnalyticsPatterns,
  fetchActions,
  CommandCenterData,
  SiteRiskItem,
  PatternItem,
  ActionItem,
  ApiReport,
} from '../services/api';
import { Zap, AlertTriangle, MapPin, GitBranch, CheckSquare, Shield, ArrowRight, RefreshCw } from 'lucide-react';
import EmptyState from '../components/EmptyState';

export default function CommandCenterPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<CommandCenterData | null>(null);
  const [sites, setSites] = useState<SiteRiskItem[]>([]);
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [actions, setActions] = useState<ActionItem[]>([]);
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
      const [ccRes, sitesRes, patternsRes, actionsRes] = await Promise.all([
        fetchCommandCenterData(),
        fetchAnalyticsSites().catch(() => [] as SiteRiskItem[]),
        fetchAnalyticsPatterns().catch(() => [] as PatternItem[]),
        fetchActions().catch(() => [] as ActionItem[]),
      ]);
      setData(ccRes);
      setSites(Array.isArray(sitesRes) ? sitesRes : []);
      setPatterns(Array.isArray(patternsRes) ? patternsRes : []);
      setActions(Array.isArray(actionsRes) ? actionsRes : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch command center metrics';
      console.error('Command center fetch error:', err);
      setError(msg);
      if (isInitial) {
        setData(null);
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

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-sm font-medium text-slate-600">Connecting to Safety Command Center...</p>
        </div>
      </div>
    );
  }

  if (!loading && (!data || data.total_reports === 0) && !error) {
    return <EmptyState />;
  }

  const criticalCount = data?.critical_alerts ?? 0;
  const sifCount = data?.sif_potential ?? 0;
  const highRiskSitesCount = data?.high_risk_sites ?? 0;
  const risingPrecursorsCount = data?.rising_precursors ?? 0;
  const openActionsCount = data?.open_actions ?? 0;
  const earlyWarningsCount = data?.early_warnings_count ?? 0;

  const COMMAND_STATS = [
    { label: 'CRITICAL ALERTS', value: criticalCount, color: 'text-red-600', bg: 'border-l-red-600', icon: Zap },
    { label: 'SIF POTENTIAL', value: sifCount, color: 'text-red-600', bg: 'border-l-red-500', icon: AlertTriangle },
    { label: 'HIGH-RISK SITES', value: highRiskSitesCount, color: 'text-orange-600', bg: 'border-l-orange-500', icon: MapPin },
    { label: 'RISING PRECURSORS', value: risingPrecursorsCount, color: 'text-indigo-600', bg: 'border-l-indigo-500', icon: GitBranch },
    { label: 'OPEN ACTIONS', value: openActionsCount, color: 'text-blue-600', bg: 'border-l-blue-600', icon: CheckSquare },
    { label: 'EARLY WARNINGS', value: earlyWarningsCount, color: 'text-amber-600', bg: 'border-l-amber-500', icon: Shield },
  ];

  return (
    <div className="space-y-8 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="section-title flex items-center gap-2.5">
            <Zap className="w-6 h-6 text-amber-500" />
            Safety Command Center
          </h1>
          <p className="section-sub">Real-time safety intelligence overview — critical items requiring immediate operational attention.</p>
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

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Big number stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-5">
        {COMMAND_STATS.map(stat => (
          <div key={stat.label} className={`card border-l-4 ${stat.bg} text-center py-6`}>
            <stat.icon className={`w-6 h-6 ${stat.color} mx-auto mb-2`} />
            <div className={`text-4xl font-extrabold ${stat.color} mb-1`}>{stat.value}</div>
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* High Priority Reports Panel */}
      {data?.high_priority_reports && data.high_priority_reports.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-600" />
              High-Priority Observations ({data.high_priority_reports.length})
            </h2>
            <button
              onClick={() => navigate('/risk-intelligence')}
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              Risk Intelligence <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            {data.high_priority_reports.slice(0, 4).map((report: ApiReport) => (
              <div
                key={report.report_id || report.id}
                className="card p-5 cursor-pointer hover:border-slate-300 transition-all border-red-200 bg-red-50/30"
                onClick={() => navigate('/ai-analysis')}
              >
                <div className="flex items-center gap-2 mb-2">
                  <RiskBadge level={(report.risk_level as any) || 'CRITICAL'} size="sm" />
                  <span className="text-xs text-slate-500 font-mono ml-auto">
                    ID: {report.report_id || report.id}
                  </span>
                </div>
                <p className="font-semibold text-slate-900 text-sm line-clamp-2">{report.description}</p>
                <div className="flex items-center gap-4 text-xs text-slate-500 mt-3 pt-2 border-t border-red-100">
                  <span>Category: <strong className="text-slate-700">{report.category}</strong></span>
                  <span>Score: <strong className="text-red-600">{report.risk_score}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* High-risk sites */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
              <MapPin className="w-4 h-4 text-blue-600" />
              High-Risk Facilities
            </h2>
            <button
              onClick={() => navigate('/sites')}
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              View All <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          <div className="card space-y-2 p-3">
            {sites.filter(s => s.risk_level !== 'LOW').slice(0, 5).map(site => (
              <div
                key={site.site}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-50 border border-transparent hover:border-slate-200 cursor-pointer transition-colors"
                onClick={() => navigate('/sites')}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-bold text-slate-900 truncate">{site.site}</span>
                    <RiskBadge level={(site.risk_level as any) || 'HIGH'} size="sm" />
                  </div>
                  <div className="text-xs text-slate-500 font-medium">
                    {site.total} reports · {site.sif} SIF potential
                  </div>
                </div>
                <div
                  className={`text-xl font-bold ${
                    site.risk_score > 50 ? 'text-red-600' : site.risk_score > 35 ? 'text-orange-600' : 'text-amber-600'
                  }`}
                >
                  {site.risk_score}
                </div>
              </div>
            ))}
            {sites.filter(s => s.risk_level !== 'LOW').length === 0 && (
              <p className="text-slate-500 text-sm p-4">No high-risk sites currently flagged.</p>
            )}
          </div>
        </section>

        {/* Recurring Safety Precursors */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-indigo-600" />
              Active Safety Precursors
            </h2>
            <button
              onClick={() => navigate('/patterns')}
              className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              View All <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          <div className="card space-y-3 p-4">
            {patterns.slice(0, 5).map(p => (
              <div key={p.name || p.category} className="space-y-1">
                <div className="flex justify-between text-xs font-medium">
                  <span className="text-slate-800 truncate mr-2">{p.name || p.category}</span>
                  <span className="text-slate-600 font-bold">{p.count || p.frequency} reports</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full"
                    style={{
                      width: `${Math.min(100, Math.round(((p.count || p.frequency || 1) / Math.max(1, data?.total_reports || 1)) * 100))}%`,
                    }}
                  />
                </div>
              </div>
            ))}
            {patterns.length === 0 && (
              <p className="text-slate-500 text-sm p-4">No recurring precursor clusters identified yet.</p>
            )}
          </div>
        </section>
      </div>

      {/* Open actions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
            <CheckSquare className="w-4 h-4 text-green-600" />
            Active Corrective Actions
          </h2>
          <button
            onClick={() => navigate('/actions')}
            className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
          >
            Manage All <ArrowRight className="w-3 h-3" />
          </button>
        </div>
        <div className="card p-3">
          {actions.filter(a => a.status !== 'COMPLETED').length === 0 ? (
            <p className="text-slate-500 text-sm p-4">No open corrective actions pending.</p>
          ) : (
            <div className="space-y-2">
              {actions
                .filter(a => a.status !== 'COMPLETED')
                .slice(0, 5)
                .map(a => (
                  <div
                    key={a.id}
                    className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 border border-transparent hover:border-slate-200 transition-colors"
                  >
                    <div className="w-2 h-2 rounded-full bg-blue-600 mt-1.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-900 leading-snug">{a.description}</p>
                      <div className="text-xs text-slate-500 mt-1">
                        Owner: <strong>{a.owner}</strong> {a.deadline ? `· Due: ${a.deadline}` : ''}
                      </div>
                    </div>
                    <span className="text-xs font-bold flex-shrink-0 px-2 py-0.5 rounded bg-blue-50 text-blue-700">
                      {a.status}
                    </span>
                  </div>
                ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}


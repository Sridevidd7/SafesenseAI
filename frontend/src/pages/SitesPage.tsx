import { useState, useEffect, useCallback } from 'react';
import EmptyState from '../components/EmptyState';
import { RiskBadge } from '../components/RiskBadge';
import { fetchAnalyticsSites, fetchAnalyticsActivities, SiteRiskItem, ActivityRiskItem } from '../services/api';
import { MapPin, Activity, AlertTriangle, RefreshCw } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function SitesPage() {
  const [siteRisks, setSiteRisks] = useState<SiteRiskItem[]>([]);
  const [activityRisks, setActivityRisks] = useState<ActivityRiskItem[]>([]);
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
      const [sitesData, activitiesData] = await Promise.all([
        fetchAnalyticsSites().catch(() => [] as SiteRiskItem[]),
        fetchAnalyticsActivities().catch(() => [] as ActivityRiskItem[]),
      ]);
      setSiteRisks(Array.isArray(sitesData) ? sitesData : []);
      setActivityRisks(Array.isArray(activitiesData) ? activitiesData : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch sites and activities risk';
      console.error('Sites/Activities fetch error:', err);
      setError(msg);
      if (isInitial) {
        setSiteRisks([]);
        setActivityRisks([]);
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

  if (loading && siteRisks.length === 0 && activityRisks.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-sm font-medium text-slate-600">Calculating facility and activity risk rankings...</p>
        </div>
      </div>
    );
  }

  if (!loading && siteRisks.length === 0 && activityRisks.length === 0 && !error) {
    return <EmptyState />;
  }

  const noSiteData = siteRisks.length === 0;
  const noActivityData = activityRisks.length === 0;

  return (
    <div className="space-y-8 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="section-title">Sites & Activities</h1>
          <p className="section-sub">Risk rankings and breakdown by facility and operational task calculated live from database records.</p>
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

      {/* Sites */}
      <section>
        <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
          <MapPin className="w-4 h-4 text-blue-600" /> Site Risk Ranking
        </h2>
        {noSiteData ? (
          <div className="card text-slate-500 text-sm flex items-center gap-2 bg-slate-50">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            Site-level analysis is unavailable because no site records were found.
          </div>
        ) : (
          <div className="grid lg:grid-cols-2 gap-6">
            <div className="space-y-3">
              {siteRisks.map((site, i) => (
                <div key={site.site} className="card flex items-center gap-4 p-4">
                  <div className="text-xl font-bold text-slate-400 w-7 flex-shrink-0 text-center">{i + 1}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-bold text-slate-900 text-sm truncate">{site.site}</span>
                      <RiskBadge level={(site.risk_level as any) || 'LOW'} size="sm" />
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs text-slate-500 font-medium">
                      <span>{site.total} reports</span>
                      <span className="text-red-600 font-semibold">{site.sif} SIF</span>
                      <span>{site.critical} critical</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1 truncate">
                      Top precursor: {site.top_precursor || 'Procedural Deviation'} · Top failure: {site.top_barrier_failure || 'Control Verification'}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className={`text-xl font-bold ${
                      site.risk_score > 50 ? 'text-red-600' : site.risk_score > 35 ? 'text-orange-600' : site.risk_score > 15 ? 'text-amber-600' : 'text-green-600'
                    }`}>{site.risk_score}</div>
                    <div className="text-xs text-slate-400 font-medium">score</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="card">
              <h3 className="text-sm font-bold text-slate-900 mb-4">SIF Potential by Site</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={siteRisks.slice(0, 6)} margin={{ left: 0, right: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="site" tick={{ fill: '#64748B', fontSize: 10 }} axisLine={{ stroke: '#E2E8F0' }} />
                  <YAxis tick={{ fill: '#64748B', fontSize: 11 }} axisLine={{ stroke: '#E2E8F0' }} />
                  <Tooltip contentStyle={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: 8, color: '#0F172A', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)' }} />
                  <Bar dataKey="sif" fill="#EF4444" name="SIF Potential" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="total" fill="#3B82F6" name="Total Reports" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </section>

      {/* Activities */}
      <section>
        <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Activity className="w-4 h-4 text-indigo-600" /> Activity Risk Ranking
        </h2>
        {noActivityData ? (
          <div className="card text-slate-500 text-sm bg-slate-50">Activity data not available in the database.</div>
        ) : (
          <div className="card p-0 overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600">#</th>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600">Activity</th>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600 text-right">Reports</th>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600 text-right">SIF Potential</th>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600 text-right">Avg Risk</th>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600">Top Barrier Failure</th>
                  <th className="py-3 px-4 text-xs font-semibold text-slate-600">Risk Level</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activityRisks.map((act, i) => (
                  <tr key={act.activity} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-4 text-slate-400 font-medium text-xs">{i + 1}</td>
                    <td className="py-3 px-4 font-semibold text-slate-800 text-xs">{act.activity}</td>
                    <td className="py-3 px-4 text-right text-slate-600 font-medium text-xs">{act.total}</td>
                    <td className="py-3 px-4 text-right text-red-600 font-bold text-xs">{act.sif}</td>
                    <td className="py-3 px-4 text-right text-slate-700 font-medium text-xs">{act.risk_score}</td>
                    <td className="py-3 px-4 text-slate-600 text-xs max-w-xs truncate">{act.top_barrier_failure || 'Permit / Verification'}</td>
                    <td className="py-3 px-4"><RiskBadge level={(act.risk_level as any) || 'LOW'} size="sm" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}


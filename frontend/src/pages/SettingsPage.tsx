import { useApp } from '../context/AppContext';
import { Shield, User, Database, Info, Trash2, Download } from 'lucide-react';

export default function SettingsPage() {
  const { user, dataset, isDemo, reports, dispatch } = useApp();

  function clearDataset() {
    if (confirm('Clear the current dataset? This will remove all loaded reports.')) {
      dispatch({ type: 'CLEAR_DATASET' });
    }
  }

  function exportReports() {
    const headers = ['id','report_type','report_text','activity','site','location','date','severity','sif_potential','risk_level','risk_score','life_saving_rule','barrier_failure','recommended_action'];
    const csv = [headers.join(','), ...reports.map(r =>
      headers.map(h => `"${String((r as unknown as Record<string, unknown>)[h] ?? '').replace(/"/g, '""')}"`).join(',')
    )].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'safesense_export.csv'; a.click();
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-in">
      <div>
        <h1 className="section-title">Settings</h1>
        <p className="section-sub">Account information, data management, and platform configuration.</p>
      </div>

      {/* User info */}
      <div className="card">
        <h2 className="font-bold text-slate-900 flex items-center gap-2 mb-4"><User className="w-4 h-4 text-blue-600" />Account</h2>
        {user ? (
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Name</span><span className="text-slate-900 font-medium">{user.name}</span></div>
            <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Email</span><span className="text-slate-900 font-medium">{user.email}</span></div>
            <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Role</span><span className="text-slate-900 font-medium">{user.role}</span></div>
            <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Site</span><span className="text-slate-900 font-medium">{user.site || 'All Sites'}</span></div>
          </div>
        ) : <p className="text-slate-500 text-sm">Not logged in.</p>}
      </div>

      {/* Dataset info */}
      <div className="card">
        <h2 className="font-bold text-slate-900 flex items-center gap-2 mb-4"><Database className="w-4 h-4 text-blue-600" />Current Dataset</h2>
        {dataset ? (
          <div className="space-y-4">
            {isDemo && (
              <div className="flex items-center gap-2 text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs font-medium">
                ⚠ Synthetic Demo Data — Not Real Organizational Data
              </div>
            )}
            <div className="grid sm:grid-cols-3 gap-4 text-sm">
              <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Filename</span><span className="text-slate-900 font-medium truncate block">{dataset.filename}</span></div>
              <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Records</span><span className="text-slate-900 font-medium">{dataset.rows}</span></div>
              <div><span className="text-slate-500 text-xs font-semibold block mb-0.5">Health Score</span><span className={`font-bold ${dataset.quality.health_score >= 80 ? 'text-green-600' : dataset.quality.health_score >= 60 ? 'text-amber-600' : 'text-red-600'}`}>{dataset.quality.health_score}/100</span></div>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={exportReports} className="btn-secondary text-sm"><Download className="w-4 h-4" />Export Reports</button>
              <button onClick={clearDataset} className="btn-danger text-sm"><Trash2 className="w-4 h-4" />Clear Dataset</button>
            </div>
          </div>
        ) : <p className="text-slate-500 text-sm">No dataset loaded.</p>}
      </div>

      {/* Model info */}
      <div className="card">
        <h2 className="font-bold text-slate-900 flex items-center gap-2 mb-4"><Shield className="w-4 h-4 text-blue-600" />AI Engine</h2>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-600">Analysis Mode</span>
            <span className="text-slate-900 font-medium">Prototype Rule-Based Engine</span>
          </div>
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-600">Life-Saving Rule Detection</span>
            <span className="text-green-600 font-semibold">Active</span>
          </div>
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-600">Barrier Failure Detection</span>
            <span className="text-green-600 font-semibold">Active</span>
          </div>
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-600">Risk Scoring</span>
            <span className="text-green-600 font-semibold">Active</span>
          </div>
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-600">Pattern Discovery</span>
            <span className="text-green-600 font-semibold">Active</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-slate-600">ML Model (Transformers)</span>
            <span className="text-slate-400 font-medium">Backend required</span>
          </div>
        </div>
      </div>

      {/* Important notices */}
      <div className="card border-amber-200 bg-amber-50/40">
        <h2 className="font-bold text-amber-900 flex items-center gap-2 mb-3"><Info className="w-4 h-4 text-amber-600" />Important Notices</h2>
        <ul className="space-y-2 text-sm text-amber-900">
          <li className="flex items-start gap-2">
            <span className="text-amber-600 font-bold">•</span>
            Risk scores are prototype calculations. They are not certified safety metrics.
          </li>
          <li className="flex items-start gap-2">
            <span className="text-amber-600 font-bold">•</span>
            SIF potential indicates elevated risk precursors — it does not predict that a fatality will occur.
          </li>
          <li className="flex items-start gap-2">
            <span className="text-amber-600 font-bold">•</span>
            All final safety decisions must be made by authorized, qualified HSE personnel.
          </li>
        </ul>
      </div>
    </div>
  );
}

/**
 * ReportsPage.tsx
 *
 * Data source: GET /api/reports  (live from SQLite DB)
 * No context reads for report data. No mock data.
 * Clean modern light theme.
 */
import { useState, useMemo } from 'react';
import { useNavigate }         from 'react-router-dom';
import { useApiReports }      from '../hooks/useApiReports';
import { ApiReport }          from '../services/api';
import {
  Search, Filter, ChevronLeft, ChevronRight,
  ArrowUpDown, Download, RefreshCw, AlertTriangle,
  FileText, Upload, CheckCircle,
} from 'lucide-react';


const PAGE_SIZE = 20;

const RISK_LEVEL_COLOR: Record<string, string> = {
  CRITICAL: 'text-red-600',
  HIGH:     'text-orange-600',
  MEDIUM:   'text-amber-600',
  LOW:      'text-green-600',
};

function SIFBadge({ value }: { value: string }) {
  return (
    <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
      value === 'YES'
        ? 'text-red-700 bg-red-50 border-red-200'
        : 'text-slate-600 bg-slate-100 border-slate-200'
    }`}>
      {value === 'YES' ? '⚡ SIF' : 'No SIF'}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const colorMap: Record<string, string> = {
    CRITICAL: 'text-red-700 bg-red-50 border-red-200',
    HIGH:     'text-orange-700 bg-orange-50 border-orange-200',
    MEDIUM:   'text-amber-700 bg-amber-50 border-amber-200',
    LOW:      'text-green-700 bg-green-50 border-green-200',
  };
  return (
    <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full border ${colorMap[level] ?? 'text-slate-600 bg-slate-100 border-slate-200'}`}>
      {level}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const navigate = useNavigate();
  const { reports, total, loading, refreshing, error, refresh } = useApiReports();
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const [search,         setSearch]         = useState('');
  const [filterSIF,      setFilterSIF]      = useState('');
  const [filterLevel,    setFilterLevel]    = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [sortCol,        setSortCol]        = useState<keyof ApiReport>('id');
  const [sortDir,        setSortDir]        = useState<'asc' | 'desc'>('desc');
  const [page,           setPage]           = useState(0);

  const handleRefresh = async () => {
    if (refreshing || loading) return;
    const result = await refresh();
    if (result) {
      setToastMessage('Reports updated with latest data');
      setTimeout(() => setToastMessage(null), 3000);
    }
  };


  // Unique categories for the dropdown — derived dynamically from fetched data
  const categories = useMemo(
    () => [...new Set(reports.map(r => r.category).filter(Boolean))].sort(),
    [reports]
  );

  // Filter
  const filtered = useMemo(() => {
    let r = reports;
    if (search) {
      const s = search.toLowerCase();
      r = r.filter(rep =>
        rep.description.toLowerCase().includes(s) ||
        String(rep.id).includes(s) ||
        rep.category.toLowerCase().includes(s)
      );
    }
    if (filterSIF)      r = r.filter(rep => rep.sif_potential === filterSIF);
    if (filterLevel)    r = r.filter(rep => rep.risk_level    === filterLevel);
    if (filterCategory) r = r.filter(rep => rep.category      === filterCategory);
    return r;
  }, [reports, search, filterSIF, filterLevel, filterCategory]);

  // Sort
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = String((a as unknown as Record<string, unknown>)[sortCol] ?? '');
      const bv = String((b as unknown as Record<string, unknown>)[sortCol] ?? '');
      return sortDir === 'asc'
        ? av.localeCompare(bv, undefined, { numeric: true })
        : bv.localeCompare(av, undefined, { numeric: true });
    });
  }, [filtered, sortCol, sortDir]);

  const paginated  = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);

  function handleSort(col: keyof ApiReport) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
    setPage(0);
  }

  function resetFilters() {
    setSearch(''); setFilterSIF(''); setFilterLevel(''); setFilterCategory('');
    setPage(0);
  }

  function exportCSV() {
    const headers = ['id', 'description', 'category', 'risk_score', 'risk_level', 'sif_potential', 'created_at'];
    const rows = sorted.map(r =>
      headers.map(h => `"${String((r as unknown as Record<string, unknown>)[h] ?? '').replace(/"/g, '""')}"`).join(',')
    );
    const csv  = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'safesense_reports_export.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  // ── Loading ───────────────────────────────────────────────────────────────
  if (loading && reports.length === 0) {
    return (
      <div className="space-y-4 animate-in">
        <div className="h-8 w-48 bg-slate-200 rounded animate-pulse mb-2" />
        <div className="h-10 bg-slate-200 rounded animate-pulse" />
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-12 bg-slate-100 rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
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
            <button onClick={refresh} disabled={loading} className="btn-secondary text-sm bg-white hover:bg-red-50 text-red-900 border-red-200 disabled:opacity-50 disabled:cursor-not-allowed">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Empty DB state ────────────────────────────────────────────────────────
  if (total === 0 || reports.length === 0) {
    return (
      <div className="animate-in">
        <div className="card flex flex-col items-center justify-center py-24 text-center">
          <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center mb-4">
            <FileText className="w-7 h-7 text-slate-400" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 mb-2">No data available</h2>
          <p className="text-slate-500 text-sm mb-6 max-w-sm">
            No reports found in the database. Upload a CSV file to populate safety reports.
          </p>
          <button onClick={() => navigate('/upload')} className="btn-primary">
            <Upload className="w-4 h-4" />
            Upload Reports
          </button>
        </div>
      </div>
    );
  }

  // ── Main render ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 animate-in relative">

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
          <h1 className="section-title">Safety Reports</h1>
          <p className="section-sub">
            {sorted.length} of {total} reports ·{' '}
            {reports.filter(r => r.sif_potential === 'YES').length} with SIF potential ·{' '}
            <span className="text-slate-500 font-medium">Live from database</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
            title="Reload from backend"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          <button onClick={exportCSV} className="btn-secondary text-sm">
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </div>


      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            className="input-field pl-9 py-2 text-sm w-60"
            placeholder="Search reports..."
          />
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          <Filter className="w-4 h-4" />
        </div>
        <select
          value={filterSIF}
          onChange={e => { setFilterSIF(e.target.value); setPage(0); }}
          className="input-field text-sm py-2 w-36"
        >
          <option value="">All SIF</option>
          <option value="YES">SIF: YES</option>
          <option value="NO">SIF: NO</option>
        </select>
        <select
          value={filterLevel}
          onChange={e => { setFilterLevel(e.target.value); setPage(0); }}
          className="input-field text-sm py-2 w-36"
        >
          <option value="">All Levels</option>
          {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(l => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        <select
          value={filterCategory}
          onChange={e => { setFilterCategory(e.target.value); setPage(0); }}
          className="input-field text-sm py-2 w-52"
        >
          <option value="">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        {(search || filterSIF || filterLevel || filterCategory) && (
          <button onClick={resetFilters} className="text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors">
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="card overflow-x-auto p-0">
        {sorted.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-slate-500 text-sm">No reports match the current filters.</p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50/80 border-b border-slate-200">
                <tr>
                  {(
                    [
                      { key: 'id' as const,            label: 'ID' },
                      { key: 'description' as const,   label: 'Description' },
                      { key: 'category' as const,      label: 'Category (LSR)' },
                      { key: 'risk_score' as const,    label: 'Score' },
                      { key: 'risk_level' as const,    label: 'Level' },
                      { key: 'sif_potential' as const, label: 'SIF' },
                      { key: 'created_at' as const,    label: 'Saved' },
                    ] as { key: keyof ApiReport; label: string }[]
                  ).map(col => (
                    <th
                      key={col.key}
                      className="text-xs font-semibold text-slate-600 py-3.5 px-4 whitespace-nowrap cursor-pointer hover:text-slate-900 select-none"
                      onClick={() => handleSort(col.key)}
                    >
                      <span className="flex items-center gap-1.5">
                        {col.label}
                        <ArrowUpDown className="w-3 h-3 text-slate-400" />
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {paginated.map(report => (
                  <tr key={report.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3.5 text-blue-600 font-mono text-xs font-semibold">{report.id}</td>
                    <td className="px-4 py-3.5 text-slate-800 max-w-md">
                      <p className="truncate text-xs leading-relaxed">{report.description}</p>
                    </td>
                    <td className="px-4 py-3.5 text-slate-600 text-xs whitespace-nowrap">
                      {report.category}
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <span className={`text-xs font-bold ${RISK_LEVEL_COLOR[report.risk_level] ?? 'text-slate-600'}`}>
                        {report.risk_score}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <RiskBadge level={report.risk_level} />
                    </td>
                    <td className="px-4 py-3.5">
                      <SIFBadge value={report.sif_potential} />
                    </td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs whitespace-nowrap">
                      {report.date || (report.created_at ? new Date(report.created_at).toLocaleDateString() : '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="flex items-center justify-between p-4 border-t border-slate-200 bg-slate-50/50">
              <span className="text-xs text-slate-500 font-medium">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, sorted.length)} of {sorted.length}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-1.5 rounded-lg border border-slate-200 hover:bg-white text-slate-600 disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-xs font-semibold text-slate-700 px-2.5">{page + 1} of {totalPages}</span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="p-1.5 rounded-lg border border-slate-200 hover:bg-white text-slate-600 disabled:opacity-30 transition-colors"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

    </div>
  );
}

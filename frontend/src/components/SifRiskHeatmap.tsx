/**
 * SifRiskHeatmap.tsx — Operational SIF Risk Concentration Explorer
 *
 * Sourced directly from GET /api/analytics/sif-heatmap (real SQLite data).
 * 6-Tier Hierarchy: Site → Unit → Area → Activity → LSR/Precursor → Failed Barrier → Reports.
 * Severity Precedence: 🔴 HIGH → 🟡 EMERGING → 🟠 MEDIUM → 🟢 LOW (mutually exclusive).
 * Fallback values ("Not Specified") are clearly flagged and distinguished.
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Layers, AlertTriangle, TrendingUp, ShieldAlert, ChevronRight,
  Filter, RotateCcw, CheckCircle, Database, FileText, ArrowRight,
  Shield, AlertOctagon, Activity, Info
} from 'lucide-react';
import { fetchSifHeatmap } from '../services/api';
import {
  SifHeatmapResponse, SifHeatmapNode, SifHeatmapSummary,
  HeatmapReportItem, HeatmapRiskLevel, SifHeatmapFilter
} from '../types';

interface BreadcrumbItem {
  level: string;
  name: string;
  filterKey: keyof SifHeatmapFilter;
  filterValue: string;
}

const RISK_BADGES: Record<HeatmapRiskLevel, { bg: string; text: string; border: string; dot: string; label: string }> = {
  HIGH: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    dot: 'bg-red-500',
    label: 'High Risk',
  },
  EMERGING: {
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-300',
    dot: 'bg-amber-500',
    label: 'Emerging',
  },
  MEDIUM: {
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    dot: 'bg-orange-500',
    label: 'Medium',
  },
  LOW: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    dot: 'bg-emerald-500',
    label: 'Low',
  },
};

const LEVEL_LABELS: Record<string, string> = {
  site: 'Site Facility',
  unit: 'Operating Unit',
  area: 'Work Area',
  activity: 'Operational Activity',
  lsr: 'SIF Precursor / LSR',
  barrier: 'Failed Barrier',
};

export default function SifRiskHeatmap() {
  const [data, setData] = useState<SifHeatmapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Active filters for progressive drill-down
  const [filters, setFilters] = useState<SifHeatmapFilter>({});
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<HeatmapReportItem | null>(null);

  // Load heatmap data from real backend endpoint
  const loadHeatmap = useCallback(async (currentFilters: SifHeatmapFilter) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchSifHeatmap(currentFilters);
      setData(response);
    } catch (err: any) {
      console.error('Failed to load SIF Heatmap:', err);
      setError(err?.message || 'Failed to retrieve SIF Risk Heatmap from backend.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHeatmap(filters);
  }, [filters, loadHeatmap]);

  // Current level nodes to display
  // If no filters: display all sites (root)
  // If site selected but no unit: display units for selected site, etc.
  const currentNodes: SifHeatmapNode[] = useMemo(() => {
    if (!data || !data.tree) return [];

    let activeLevelList = data.tree;

    // If site filtered, descend into that site's units
    if (filters.site) {
      const siteNode = activeLevelList.find(n => n.name === filters.site);
      if (siteNode && siteNode.children && siteNode.children.length > 0) {
        activeLevelList = siteNode.children;

        // If unit filtered, descend into area
        if (filters.unit) {
          const unitNode = activeLevelList.find(n => n.name === filters.unit);
          if (unitNode && unitNode.children && unitNode.children.length > 0) {
            activeLevelList = unitNode.children;

            // If area filtered, descend into activity
            if (filters.area) {
              const areaNode = activeLevelList.find(n => n.name === filters.area);
              if (areaNode && areaNode.children && areaNode.children.length > 0) {
                activeLevelList = areaNode.children;

                // If activity filtered, descend into LSR
                if (filters.activity) {
                  const actNode = activeLevelList.find(n => n.name === filters.activity);
                  if (actNode && actNode.children && actNode.children.length > 0) {
                    activeLevelList = actNode.children;

                    // If LSR filtered, descend into barrier
                    if (filters.lsr) {
                      const lsrNode = activeLevelList.find(n => n.name === filters.lsr);
                      if (lsrNode && lsrNode.children && lsrNode.children.length > 0) {
                        activeLevelList = lsrNode.children;
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

    return activeLevelList;
  }, [data, filters]);

  // Drill down into a child node
  const handleDrillDown = (node: SifHeatmapNode) => {
    const nextFilters: SifHeatmapFilter = { ...filters };
    let filterKey: keyof SifHeatmapFilter = 'site';

    if (node.level === 'site') {
      nextFilters.site = node.name;
      filterKey = 'site';
    } else if (node.level === 'unit') {
      nextFilters.unit = node.name;
      filterKey = 'unit';
    } else if (node.level === 'area') {
      nextFilters.area = node.name;
      filterKey = 'area';
    } else if (node.level === 'activity') {
      nextFilters.activity = node.name;
      filterKey = 'activity';
    } else if (node.level === 'lsr') {
      nextFilters.lsr = node.name;
      filterKey = 'lsr';
    } else if (node.level === 'barrier') {
      nextFilters.barrier = node.name;
      filterKey = 'barrier';
    }

    setFilters(nextFilters);
    setBreadcrumbs(prev => [
      ...prev,
      {
        level: node.level,
        name: node.name,
        filterKey,
        filterValue: node.name,
      },
    ]);
  };

  // Step back via breadcrumb
  const handleBreadcrumbClick = (index: number) => {
    if (index === -1) {
      // Clicked "All Sites" root
      setFilters({});
      setBreadcrumbs([]);
      return;
    }

    const clickedCrumb = breadcrumbs[index];
    const newBreadcrumbs = breadcrumbs.slice(0, index + 1);
    const newFilters: SifHeatmapFilter = {};

    newBreadcrumbs.forEach(crumb => {
      newFilters[crumb.filterKey] = crumb.filterValue;
    });

    setFilters(newFilters);
    setBreadcrumbs(newBreadcrumbs);
  };

  const handleResetFilters = () => {
    setFilters({});
    setBreadcrumbs([]);
    setSelectedReport(null);
  };

  const summary = data?.summary;
  const reportsList = data?.reports || [];

  return (
    <div className="space-y-6">

      {/* Header and Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="p-1.5 rounded-lg bg-red-100 text-red-700">
              <ShieldAlert className="w-5 h-5" />
            </span>
            <h2 className="text-xl font-bold text-slate-900">
              SIF Risk Concentration Explorer
            </h2>
          </div>
          <p className="text-sm text-slate-500">
            Multi-tier operational risk concentration across Site → Unit → Area → Activity → Precursor / LSR → Barrier Failure.
          </p>
        </div>

        {breadcrumbs.length > 0 && (
          <button
            onClick={handleResetFilters}
            className="btn-secondary text-xs flex items-center gap-1.5 self-start sm:self-auto"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset to Site Overview
          </button>
        )}
      </div>

      {/* KPI Concentration Metrics */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
          <div className="card border-l-4 border-l-blue-500 py-3.5 px-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Scattered Reports</p>
            <p className="text-2xl font-bold text-slate-900">{summary.total_reports}</p>
            <p className="text-xs text-slate-400 mt-0.5">Matching active view</p>
          </div>

          <div className="card border-l-4 border-l-red-500 py-3.5 px-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">SIF Precursors</p>
            <p className="text-2xl font-bold text-red-600">{summary.total_precursors}</p>
            <p className="text-xs text-slate-400 mt-0.5">{summary.overall_density}% precursor density</p>
          </div>

          <div className="card border-l-4 border-l-rose-600 py-3.5 px-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">High Risk Hotspots</p>
            <p className="text-2xl font-bold text-rose-600">{summary.high_risk_concentrations}</p>
            <p className="text-xs text-slate-400 mt-0.5">🔴 Severe concentration</p>
          </div>

          <div className="card border-l-4 border-l-amber-500 py-3.5 px-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Emerging Risk</p>
            <p className="text-2xl font-bold text-amber-600">{summary.emerging_concentrations}</p>
            <p className="text-xs text-slate-400 mt-0.5">🟡 Positive 30d trend</p>
          </div>

          <div className="card border-l-4 border-l-indigo-500 py-3.5 px-4 col-span-2 md:col-span-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Top Concentration</p>
            <p className="text-sm font-bold text-slate-900 truncate" title={summary.top_concentration}>
              {summary.top_concentration}
            </p>
            <p className="text-xs text-slate-400 mt-0.5">Highest severity node</p>
          </div>
        </div>
      )}

      {/* Interactive Breadcrumb Path */}
      <div className="bg-slate-100/80 rounded-xl p-3 flex items-center flex-wrap gap-1.5 text-xs text-slate-600 border border-slate-200">
        <span className="font-semibold text-slate-500 flex items-center gap-1 mr-1">
          <Filter className="w-3.5 h-3.5" />
          Drill-down:
        </span>
        <button
          onClick={() => handleBreadcrumbClick(-1)}
          className={`font-medium px-2 py-1 rounded-md transition-colors ${
            breadcrumbs.length === 0
              ? 'bg-blue-600 text-white shadow-xs font-semibold'
              : 'hover:bg-slate-200 text-blue-700'
          }`}
        >
          All Sites
        </button>

        {breadcrumbs.map((crumb, idx) => {
          const isLast = idx === breadcrumbs.length - 1;
          return (
            <React.Fragment key={crumb.level + idx}>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
              <button
                onClick={() => handleBreadcrumbClick(idx)}
                className={`px-2 py-1 rounded-md transition-colors ${
                  isLast
                    ? 'bg-blue-600 text-white shadow-xs font-semibold'
                    : 'hover:bg-slate-200 text-blue-700 font-medium'
                }`}
              >
                <span className="text-[10px] text-blue-200 block uppercase font-bold tracking-wider leading-none mb-0.5">
                  {LEVEL_LABELS[crumb.level] || crumb.level}
                </span>
                {crumb.name}
              </button>
            </React.Fragment>
          );
        })}
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-900 text-sm flex items-start gap-3">
          <AlertOctagon className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-bold">Failed to load risk concentration data</p>
            <p className="text-xs text-red-700 mt-1">{error}</p>
            <button
              onClick={() => loadHeatmap(filters)}
              className="mt-2 btn-secondary text-xs bg-white text-red-800 border-red-300"
            >
              Retry Connection
            </button>
          </div>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !data && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="animate-pulse bg-slate-100 rounded-xl p-5 h-44 border border-slate-200" />
          ))}
        </div>
      )}

      {/* Node Heatmap Explorer Cards */}
      {!loading && currentNodes.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium px-1">
            <span>
              Showing {currentNodes.length} {currentNodes[0]?.level ? LEVEL_LABELS[currentNodes[0].level] : 'level'} entries
            </span>
            <span className="text-[11px] text-slate-400">Click a card to filter deeper into the hierarchy</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {currentNodes.map(node => {
              const badge = RISK_BADGES[node.risk_level] || RISK_BADGES.LOW;
              const hasChildren = node.children && node.children.length > 0;
              const isFallback = node.is_fallback;

              return (
                <div
                  key={node.id}
                  onClick={() => handleDrillDown(node)}
                  className={`card relative overflow-hidden transition-all duration-200 cursor-pointer hover:shadow-md hover:border-blue-300 flex flex-col justify-between ${
                    isFallback ? 'bg-slate-50/70 border-dashed border-slate-300' : 'bg-white'
                  }`}
                >
                  {/* Top Level Bar & Badges */}
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                          {LEVEL_LABELS[node.level] || node.level}
                        </span>
                        <h4 className="font-bold text-slate-900 text-base leading-snug flex items-center gap-1.5">
                          {node.name}
                          {isFallback && (
                            <span className="text-[11px] font-normal text-slate-400 italic bg-slate-200/60 px-1.5 py-0.5 rounded">
                              (Not Specified)
                            </span>
                          )}
                        </h4>
                      </div>

                      {/* Risk Badge */}
                      <span className={`text-xs font-bold px-2.5 py-1 rounded-full border flex items-center gap-1.5 flex-shrink-0 ${badge.bg} ${badge.text} ${badge.border}`}>
                        <span className={`w-2 h-2 rounded-full ${badge.dot}`} />
                        {badge.label}
                      </span>
                    </div>

                    {/* Precursor metrics row */}
                    <div className="grid grid-cols-2 gap-2 my-3 p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                      <div>
                        <span className="text-[11px] text-slate-500 font-medium block">SIF Precursors</span>
                        <span className="text-lg font-bold text-slate-900">
                          {node.sif_count}
                          <span className="text-xs text-slate-400 font-normal"> / {node.total_reports}</span>
                        </span>
                      </div>
                      <div>
                        <span className="text-[11px] text-slate-500 font-medium block">Precursor Rate</span>
                        <span className="text-lg font-bold text-slate-900">
                          {node.precursor_density}%
                        </span>
                      </div>
                    </div>

                    {/* Details row: trend & failed barrier */}
                    <div className="space-y-1.5 text-xs text-slate-600 mb-2">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400">Period Trend:</span>
                        <span className={`font-semibold flex items-center gap-1 ${
                          node.trend_pct !== null && node.trend_pct > 0 ? 'text-amber-700' :
                          node.trend_pct !== null && node.trend_pct < 0 ? 'text-emerald-700' :
                          'text-slate-600'
                        }`}>
                          <TrendingUp className="w-3.5 h-3.5" />
                          {node.trend_label}
                        </span>
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-slate-400">Top Failed Barrier:</span>
                        <span className="font-semibold text-slate-800 truncate max-w-[160px]" title={node.top_barrier}>
                          {node.top_barrier}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card Footer action */}
                  <div className="pt-2.5 mt-2 border-t border-slate-100 flex items-center justify-between text-xs text-blue-600 font-semibold group-hover:text-blue-800">
                    <span>
                      {hasChildren ? `Drill down to ${LEVEL_LABELS[node.children![0].level] || 'sub-level'}` : 'View corresponding reports'}
                    </span>
                    <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!loading && currentNodes.length === 0 && (
        <div className="card py-16 text-center text-slate-500">
          <Database className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="font-bold text-slate-800 text-base mb-1">No matching concentration nodes</h3>
          <p className="text-xs text-slate-400 max-w-sm mx-auto mb-4">
            No safety reports match the current filter path. Try stepping back to a higher level.
          </p>
          <button onClick={handleResetFilters} className="btn-secondary text-xs">
            Back to Site Overview
          </button>
        </div>
      )}

      {/* Reports Deep-Dive Drawer / Table */}
      {reportsList.length > 0 && (
        <div className="card border border-slate-200 mt-6 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-600" />
              <h3 className="font-bold text-slate-900 text-sm">
                Underlying Safety Reports ({reportsList.length} total)
              </h3>
            </div>
            <span className="text-xs text-slate-400">
              Live SQLite dataset records
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <th className="py-2.5 px-3">Report ID</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Location (Unit / Area)</th>
                  <th className="py-2.5 px-3">LSR Category</th>
                  <th className="py-2.5 px-3">Failed Barrier</th>
                  <th className="py-2.5 px-3 text-center">SIF</th>
                  <th className="py-2.5 px-3">Risk Level</th>
                  <th className="py-2.5 px-3">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {reportsList.slice(0, 15).map(report => (
                  <tr
                    key={report.report_id}
                    onClick={() => setSelectedReport(report)}
                    className="hover:bg-blue-50/50 cursor-pointer transition-colors"
                  >
                    <td className="py-2 px-3 font-mono font-bold text-blue-700 whitespace-nowrap">
                      {report.report_id.slice(0, 8)}...
                    </td>
                    <td className="py-2 px-3 text-slate-600 whitespace-nowrap">
                      {report.date || 'N/A'}
                    </td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      <span className="font-medium text-slate-900">{report.unit || 'Not Specified'}</span>
                      <span className="text-slate-400 block text-[11px]">{report.area || 'Not Specified'}</span>
                    </td>
                    <td className="py-2 px-3 font-medium text-slate-800 whitespace-nowrap">
                      {report.category}
                    </td>
                    <td className="py-2 px-3 text-slate-700 whitespace-nowrap">
                      {report.barrier_failure || 'Unspecified'}
                    </td>
                    <td className="py-2 px-3 text-center whitespace-nowrap">
                      <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                        report.sif_potential === 'YES' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'
                      }`}>
                        {report.sif_potential}
                      </span>
                    </td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        report.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                        report.risk_level === 'HIGH'     ? 'bg-orange-100 text-orange-700' :
                        report.risk_level === 'MEDIUM'   ? 'bg-amber-100 text-amber-700' :
                        'bg-emerald-100 text-emerald-700'
                      }`}>
                        {report.risk_level}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-600 max-w-xs truncate" title={report.description}>
                      {report.pii_detected && (
                        <span className="mr-1.5 text-[9px] bg-purple-100 text-purple-700 font-bold px-1.5 py-0.5 rounded border border-purple-200">
                          PII Redacted
                        </span>
                      )}
                      {report.description}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {reportsList.length > 15 && (
            <p className="text-xs text-center text-slate-400 pt-1">
              Showing first 15 of {reportsList.length} matching reports.
            </p>
          )}
        </div>
      )}

      {/* Single Report Detail Modal */}
      {selectedReport && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4 border border-slate-200">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] font-bold uppercase text-slate-400">Report Deep-Dive</span>
                <h3 className="font-bold text-slate-900 text-lg">Report #{selectedReport.report_id}</h3>
              </div>
              <button
                onClick={() => setSelectedReport(null)}
                className="text-slate-400 hover:text-slate-700 text-sm font-bold p-1"
              >
                ✕
              </button>
            </div>

            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-sm text-slate-800 leading-relaxed">
              {selectedReport.pii_detected && (
                <div className="mb-2 p-2 bg-purple-50 border border-purple-200 rounded-lg text-xs text-purple-800 flex items-center gap-1.5 font-medium">
                  <Shield className="w-4 h-4 text-purple-600 flex-shrink-0" />
                  <span>Privacy Protection Applied: Sanitized sensitive identifiers ({selectedReport.pii_types || 'names/IDs'})</span>
                </div>
              )}
              {selectedReport.description}
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-slate-50 p-2.5 rounded-lg">
                <span className="text-slate-400 block mb-0.5">Site &amp; Hierarchy:</span>
                <span className="font-semibold text-slate-800">
                  {selectedReport.site} → {selectedReport.unit || 'Not Specified'} → {selectedReport.area || 'Not Specified'}
                </span>
              </div>
              <div className="bg-slate-50 p-2.5 rounded-lg">
                <span className="text-slate-400 block mb-0.5">LSR &amp; Failed Barrier:</span>
                <span className="font-semibold text-slate-800">
                  {selectedReport.category} · {selectedReport.barrier_failure || 'Unspecified'}
                </span>
              </div>
              <div className="bg-slate-50 p-2.5 rounded-lg">
                <span className="text-slate-400 block mb-0.5">Risk Score:</span>
                <span className="font-bold text-slate-900">{selectedReport.risk_score} / 100 ({selectedReport.risk_level})</span>
              </div>
              <div className="bg-slate-50 p-2.5 rounded-lg">
                <span className="text-slate-400 block mb-0.5">SIF Potential:</span>
                <span className={`font-bold ${selectedReport.sif_potential === 'YES' ? 'text-red-600' : 'text-slate-700'}`}>
                  {selectedReport.sif_potential}
                </span>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedReport(null)}
                className="btn-primary text-xs"
              >
                Close Report
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

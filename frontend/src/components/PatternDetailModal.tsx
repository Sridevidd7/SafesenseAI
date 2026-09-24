import React, { useEffect } from 'react';
import { PatternItem } from '../services/api';
import { RiskBadge, SIFBadge } from './RiskBadge';
import { X, GitBranch, MapPin, Repeat, TrendingUp, TrendingDown, Minus, ShieldAlert, FileText, CheckCircle2 } from 'lucide-react';

interface PatternDetailModalProps {
  pattern: PatternItem | null;
  onClose: () => void;
}

export default function PatternDetailModal({ pattern, onClose }: PatternDetailModalProps) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!pattern) return null;

  const title = pattern.theme || pattern.name || pattern.category;
  const count = pattern.count || pattern.frequency || 0;
  const sifCount = pattern.sif_count || 0;
  const trend = pattern.trend || 'stable';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pattern-modal-title"
    >
      <div
        className="bg-white rounded-2xl max-w-2xl w-full shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-200 bg-slate-50/70 flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              {pattern.cluster_id && (
                <span className="text-xs font-mono font-bold bg-slate-900 text-white px-2 py-0.5 rounded">
                  {pattern.cluster_id}
                </span>
              )}
              <RiskBadge level={pattern.risk_level || 'HIGH'} size="sm" />
              {sifCount > 0 ? (
                <SIFBadge potential="YES" size="sm" />
              ) : (
                <SIFBadge potential="NO" size="sm" />
              )}
              {pattern.is_repeated && (
                <span className="text-[11px] font-bold bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full inline-flex items-center gap-1">
                  <Repeat className="w-3 h-3 text-amber-700" />
                  Recurring Pattern (&gt;=3 reports)
                </span>
              )}
            </div>

            <h3 id="pattern-modal-title" className="text-base font-bold text-slate-900">
              {title}
            </h3>
          </div>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-200/60 transition-colors"
            aria-label="Close pattern details"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 overflow-y-auto space-y-5">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
              <span className="text-[11px] font-semibold text-slate-500 uppercase block mb-0.5">Report Count</span>
              <span className="text-2xl font-bold text-slate-900">{count}</span>
              <span className="text-[10px] text-slate-500 block">correlations</span>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
              <span className="text-[11px] font-semibold text-slate-500 uppercase block mb-0.5">SIF Incidents</span>
              <span className={`text-2xl font-bold ${sifCount > 0 ? 'text-red-600' : 'text-slate-700'}`}>
                {sifCount}
              </span>
              <span className="text-[10px] text-slate-500 block">severe precursors</span>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
              <span className="text-[11px] font-semibold text-slate-500 uppercase block mb-0.5">Avg Risk</span>
              <span className="text-2xl font-bold text-blue-600">{pattern.avg_risk || pattern.risk_score || 50}</span>
              <span className="text-[10px] text-slate-500 block">score / 100</span>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
              <span className="text-[11px] font-semibold text-slate-500 uppercase block mb-0.5">Trajectory</span>
              <div className="flex items-center justify-center gap-1">
                {trend === 'increasing' ? (
                  <TrendingUp className="w-4 h-4 text-red-600" />
                ) : trend === 'decreasing' ? (
                  <TrendingDown className="w-4 h-4 text-emerald-600" />
                ) : (
                  <Minus className="w-4 h-4 text-slate-500" />
                )}
                <span className={`text-base font-bold capitalize ${
                  trend === 'increasing' ? 'text-red-600' : trend === 'decreasing' ? 'text-emerald-600' : 'text-slate-700'
                }`}>
                  {trend}
                </span>
              </div>
              <span className="text-[10px] text-slate-500 block">trend direction</span>
            </div>
          </div>

          {/* Section 1: Observed Factual Data */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-slate-700" />
              <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                1. Observed Incident Data (Single Source of Truth)
              </h4>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-2.5 text-xs">
              <div className="grid sm:grid-cols-2 gap-2 text-slate-700">
                <div>
                  <span className="font-semibold text-slate-500 block text-[10px] uppercase">Category / LSR:</span>
                  <span className="font-bold text-slate-900">{pattern.category}</span>
                </div>
                <div>
                  <span className="font-semibold text-slate-500 block text-[10px] uppercase">Identified Barrier:</span>
                  <span className="font-bold text-slate-900">{pattern.barrier || 'Control Verification'}</span>
                </div>
              </div>

              {pattern.sites && pattern.sites.length > 0 && (
                <div>
                  <span className="font-semibold text-slate-500 block text-[10px] uppercase mb-1">
                    Affected Operating Facilities ({pattern.sites.length}):
                  </span>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    {pattern.sites.map(site => (
                      <span key={site} className="px-2.5 py-0.5 rounded-md bg-white border border-slate-200 font-semibold text-slate-800">
                        {site}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Representative Sample Observations */}
            {pattern.sample_descriptions && pattern.sample_descriptions.length > 0 && (
              <div className="space-y-2">
                <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
                  Cluster Incident Excerpts ({pattern.sample_descriptions.length})
                </span>
                <div className="space-y-2">
                  {pattern.sample_descriptions.map((desc, i) => (
                    <div
                      key={i}
                      className="p-3 bg-white rounded-lg border border-slate-200 text-xs text-slate-700 italic leading-relaxed"
                    >
                      "{desc}"
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Section 2: Pattern Intelligence Interpretation */}
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-indigo-600" />
              <h4 className="text-xs font-bold text-indigo-950 uppercase tracking-wider">
                2. Pattern Engine Synthesis
              </h4>
            </div>

            <div className="p-3.5 bg-indigo-50/60 border border-indigo-200 rounded-xl space-y-1.5 text-xs text-indigo-950">
              <p className="font-semibold leading-relaxed">
                {pattern.simplified_insight || pattern.description || 'Similarity cluster synthesized from recurring safety reports.'}
              </p>
              <p className="text-[11px] text-indigo-800/90 leading-relaxed">
                Note: SafeSense clusters reports using Jaccard token similarity with domain barrier weighting. Observed patterns denote correlation across operational logs, not direct causality.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs">
          <span className="text-slate-500 font-medium">
            Pattern ID: {pattern.cluster_id || 'N/A'} · Source: SQLite
          </span>
          <button onClick={onClose} className="btn-secondary text-xs py-1.5 px-3">
            Close Inspection
          </button>
        </div>
      </div>
    </div>
  );
}

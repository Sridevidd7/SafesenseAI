import React, { useState } from 'react';
import { RiskFactor, FactorBreakdownDetail } from '../types';
import { Sliders, ChevronDown, ChevronUp, ShieldAlert, CheckCircle, Info } from 'lucide-react';

interface FactorBreakdownViewProps {
  factors?: RiskFactor[];
  breakdown?: Record<string, FactorBreakdownDetail>;
  defaultExpanded?: boolean;
  className?: string;
}

export default function FactorBreakdownView({
  factors = [],
  breakdown = {},
  defaultExpanded = true,
  className = '',
}: FactorBreakdownViewProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Normalize list of factor items merging array and dictionary representations
  const normalizedFactors = React.useMemo(() => {
    // If breakdown dict exists and has keys, prefer it for full details
    const keys = Object.keys(breakdown);
    if (keys.length > 0) {
      return keys.map(k => breakdown[k]);
    }
    return factors;
  }, [factors, breakdown]);

  if (!normalizedFactors || normalizedFactors.length === 0) {
    return null;
  }

  const totalScore = normalizedFactors.reduce((acc, f) => acc + (f.score || 0), 0);
  const totalMax = normalizedFactors.reduce((acc, f) => acc + (f.max_score || 100), 0);

  return (
    <div className={`card p-4 space-y-3 border-slate-200 bg-white ${className}`}>
      {/* Header with expand/collapse */}
      <div
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
        className="flex items-center justify-between cursor-pointer select-none"
      >
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-blue-600" aria-hidden="true" />
          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            Five-Factor Explainable Risk Breakdown
          </h4>
          <span className="text-[11px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
            {totalScore} / {totalMax} pts
          </span>
        </div>

        <button
          type="button"
          className="text-slate-400 hover:text-slate-700 p-1"
          aria-label={expanded ? 'Collapse factor breakdown' : 'Expand factor breakdown'}
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      <p className="text-[11px] text-slate-500 leading-normal">
        SafeSense evaluates 5 deterministic safety dimensions to explain exactly why this risk level was assigned.
      </p>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-slate-100">
          {normalizedFactors.map(factor => {
            const pct = Math.min(100, Math.round(((factor.score || 0) / (factor.max_score || 1)) * 100));

            // Color coding based on severity of contribution
            const barColor =
              pct >= 80 ? 'bg-red-500' : pct >= 45 ? 'bg-amber-500' : pct > 0 ? 'bg-blue-500' : 'bg-emerald-500';

            const scoreBadgeColor =
              pct >= 80
                ? 'bg-red-50 text-red-800 border-red-200'
                : pct >= 45
                ? 'bg-amber-50 text-amber-800 border-amber-200'
                : pct > 0
                ? 'bg-blue-50 text-blue-800 border-blue-200'
                : 'bg-emerald-50 text-emerald-800 border-emerald-200';

            return (
              <div key={factor.name} className="p-3 bg-slate-50/70 border border-slate-200 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-900">{factor.name}</span>
                  <span className={`text-[11px] font-extrabold px-2 py-0.5 rounded border ${scoreBadgeColor}`}>
                    {factor.score} / {factor.max_score} pts
                  </span>
                </div>

                {/* Progress bar */}
                <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>

                {/* Deterministic Explanation Reason */}
                {factor.reason && (
                  <p className="text-[11px] text-slate-700 leading-relaxed pt-0.5">
                    <strong>Reason:</strong> {factor.reason}
                  </p>
                )}

                {/* Supporting Evidence Chips */}
                {factor.evidence && factor.evidence.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap pt-1">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase">Evidence:</span>
                    {factor.evidence.map((ev, i) => (
                      <span
                        key={i}
                        className="text-[10px] font-mono bg-white text-slate-700 px-2 py-0.5 rounded border border-slate-200 font-medium"
                      >
                        ✓ "{ev}"
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

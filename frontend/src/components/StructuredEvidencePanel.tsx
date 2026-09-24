import React from 'react';
import { StructuredEvidenceItem } from '../types';
import { CheckCircle2, AlertOctagon, ShieldCheck, Info, Clock, Tag } from 'lucide-react';

interface StructuredEvidencePanelProps {
  structuredEvidence?: StructuredEvidenceItem[];
  safetyConcepts?: string[];
  temporalSequence?: string;
  className?: string;
}

const STATE_CONFIG: Record<string, { bg: string; text: string; border: string; label: string; icon: typeof CheckCircle2 }> = {
  ACTIVE_VIOLATION: {
    bg: 'bg-red-50',
    text: 'text-red-900',
    border: 'border-red-300',
    label: 'ACTIVE VIOLATION',
    icon: AlertOctagon,
  },
  PREVENTED: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-900',
    border: 'border-emerald-300',
    label: 'PREVENTED CONTROL',
    icon: ShieldCheck,
  },
  POSITIVE_CONTROL: {
    bg: 'bg-blue-50',
    text: 'text-blue-900',
    border: 'border-blue-300',
    label: 'POSITIVE CONTROL',
    icon: CheckCircle2,
  },
  CONTEXT_ONLY: {
    bg: 'bg-slate-100',
    text: 'text-slate-800',
    border: 'border-slate-300',
    label: 'OPERATIONAL CONTEXT',
    icon: Info,
  },
};

const TEMPORAL_LABELS: Record<string, { label: string; desc: string; cls: string }> = {
  PREVENTIVE_BEFORE_EXPOSURE: {
    label: 'Preventive Stop-Work (Pre-Exposure)',
    desc: 'Work was halted or controls applied before hazard exposure occurred.',
    cls: 'bg-emerald-50 text-emerald-800 border-emerald-300',
  },
  UNSAFE_WITH_INTERVENTION: {
    label: 'Intervention Mitigated (Active Exposure)',
    desc: 'Unsafe condition began but was actively interrupted by personnel or supervisors.',
    cls: 'bg-amber-50 text-amber-900 border-amber-300',
  },
  PURE_UNSAFE: {
    label: 'Active Unmitigated Violation',
    desc: 'Activity was performed without required safety barriers; active SIF precursor.',
    cls: 'bg-red-50 text-red-900 border-red-300',
  },
  PURE_SAFE: {
    label: 'Compliant Execution',
    desc: 'Full barrier adherence and positive safety controls verified.',
    cls: 'bg-blue-50 text-blue-900 border-blue-300',
  },
};

export default function StructuredEvidencePanel({
  structuredEvidence = [],
  safetyConcepts = [],
  temporalSequence,
  className = '',
}: StructuredEvidencePanelProps) {
  const temporalInfo = temporalSequence ? TEMPORAL_LABELS[temporalSequence] : null;

  return (
    <div className={`card p-4 space-y-3.5 border-slate-200 bg-white ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <div className="flex items-center gap-2">
          <Tag className="w-4 h-4 text-blue-600" aria-hidden="true" />
          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            Structured Evidence &amp; Concept Extraction
          </h4>
        </div>

        {temporalInfo && (
          <div className="flex items-center gap-1.5" title={temporalInfo.desc}>
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${temporalInfo.cls}`}>
              {temporalInfo.label}
            </span>
          </div>
        )}
      </div>

      {/* Safety Concepts Badges */}
      {safetyConcepts.length > 0 && (
        <div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
            Detected Safety Concepts ({safetyConcepts.length})
          </span>
          <div className="flex flex-wrap gap-1.5">
            {safetyConcepts.map((concept, idx) => (
              <span
                key={idx}
                className="text-[11px] font-mono font-medium bg-slate-100 text-slate-800 border border-slate-200 px-2 py-0.5 rounded-md"
              >
                #{concept}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Structured Evidence Items */}
      {structuredEvidence.length > 0 ? (
        <div className="space-y-2">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">
            Extracted Grounding Evidence ({structuredEvidence.length})
          </span>
          <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden bg-slate-50/50">
            {structuredEvidence.map((item, idx) => {
              const stateStyle = STATE_CONFIG[item.state] || STATE_CONFIG.CONTEXT_ONLY;
              const Icon = stateStyle.icon;

              return (
                <div key={idx} className="p-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white">
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-slate-900">
                        "{item.source_phrase}"
                      </span>
                      <span className="text-[10px] font-mono bg-slate-100 text-slate-600 px-1.5 py-0.2 rounded border border-slate-200">
                        {item.concept}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-[11px] text-slate-500">
                      {item.related_barrier && (
                        <span>
                          Barrier: <strong className="text-slate-700">{item.related_barrier}</strong>
                        </span>
                      )}
                      {item.related_rule && (
                        <span>
                          · Rule: <strong className="text-slate-700">{item.related_rule}</strong>
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 self-start sm:self-auto flex-shrink-0">
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded border ${stateStyle.bg} ${stateStyle.text} ${stateStyle.border}`}
                    >
                      <Icon className="w-3 h-3" />
                      {stateStyle.label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="text-xs text-slate-500 italic p-3 bg-slate-50 rounded-lg border border-slate-100">
          No structured concept anomalies flagged in this report. Classification based on baseline operational keywords.
        </div>
      )}
    </div>
  );
}

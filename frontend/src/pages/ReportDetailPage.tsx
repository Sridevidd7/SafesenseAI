import { useParams, useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { RiskBadge, SIFBadge } from '../components/RiskBadge';
import RiskGauge from '../components/RiskGauge';
import { analyzeReport } from '../utils/riskEngine';
import { useMemo, useState, useEffect, useCallback } from 'react';
import { ArrowLeft, CheckCircle, XCircle, RotateCcw, Shield, MessageSquare, Clock, User as UserIcon, AlertTriangle, Cpu } from 'lucide-react';
import {
  fetchReviewsByReport,
  createReview,
  ReviewItem,
  fetchReportExplanation,
  LlmExplanationResponse,
  analyzeReportApi,
} from '../services/api';
import { ReportAnalysis } from '../types';
import StructuredEvidencePanel from '../components/StructuredEvidencePanel';
import FactorBreakdownView from '../components/FactorBreakdownView';

const DECISION_BADGE: Record<string, { label: string; bg: string; text: string; border: string }> = {
  'CONFIRMED': { label: 'Confirmed', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  'CORRECTED': { label: 'Corrected', bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200' },
  'REJECTED':  { label: 'Rejected',  bg: 'bg-rose-50',    text: 'text-rose-700',    border: 'border-rose-200' },
};

export default function ReportDetailPage() {
  const { id } = useParams();
  const { reports, user } = useApp();
  const navigate = useNavigate();

  const report = reports.find(r => String(r.id) === String(id));
  const numericReportId = id ? parseInt(id, 10) : null;

  const [comment, setComment] = useState('');
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [loadingReviews, setLoadingReviews] = useState(false);
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const [apiAnalysis, setApiAnalysis] = useState<ReportAnalysis | null>(null);
  const [explanation, setExplanation] = useState<LlmExplanationResponse | null>(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);

  const localAnalysis = useMemo(() => report ? analyzeReport(report) : null, [report]);
  const analysis = apiAnalysis || localAnalysis;

  const similarReports = useMemo(() => {
    if (!report || !analysis) return [];
    return reports
      .filter(r => String(r.id) !== String(report.id) && r.life_saving_rule === analysis.life_saving_rule)
      .slice(0, 4);
  }, [report, reports, analysis]);

  // Fetch full Phase 2 backend analysis including structured evidence & factor breakdown
  useEffect(() => {
    if (!report) return;
    analyzeReportApi({
      report_text: report.report_text,
      severity: report.severity,
      life_saving_rule: report.life_saving_rule,
    })
      .then(res => setApiAnalysis(res))
      .catch(() => {
        // Fallback to local deterministic analysis
      });
  }, [report]);

  const loadReviews = useCallback(async () => {
    if (!numericReportId || isNaN(numericReportId)) return;
    setLoadingReviews(true);
    setReviewError(null);
    try {
      const data = await fetchReviewsByReport(numericReportId);
      setReviews(data);
    } catch {
      // If report has no reviews yet, keep empty array
      setReviews([]);
    } finally {
      setLoadingReviews(false);
    }
  }, [numericReportId]);

  useEffect(() => {
    loadReviews();
  }, [loadReviews]);

  useEffect(() => {
    if (!report) return;
    setLoadingExplanation(true);
    const barriers = analysis?.barrier_failures || [analysis?.barrier_failure || 'Unknown'];
    fetchReportExplanation(numericReportId || undefined, {
      description: report.report_text,
      life_saving_rule: analysis?.life_saving_rule,
      barrier_failures: barriers,
      risk_score: analysis?.risk_score,
      risk_level: analysis?.risk_level,
      sif_potential: report.sif_potential,
      confidence: analysis?.confidence || 0.95
    })
      .then(res => setExplanation(res))
      .catch(() => {
        setExplanation({
          root_cause: `${analysis?.life_saving_rule || 'Safety rule'} violation due to ${analysis?.barrier_failure || 'barrier failure'}.`,
          risk_explanation: `Evaluated as ${analysis?.risk_level || 'LOW'} risk (${analysis?.risk_score || 0}/100).`,
          potential_consequence: `Hazard exposure under ${analysis?.life_saving_rule || 'general'} conditions.`,
          recommended_actions: analysis?.recommended_actions || ['Stop unsafe work immediately', 'Apply safety controls', 'Verify before resuming'],
          source: 'fallback_rule_based',
          validation_passed: false,
          validation_reason: 'network_fallback',
          cached: false
        });
      })
      .finally(() => setLoadingExplanation(false));
  }, [report, numericReportId, analysis]);

  async function submitReview(decision: 'CONFIRMED' | 'CORRECTED' | 'REJECTED') {
    if (!numericReportId || isNaN(numericReportId) || submittingReview) return;
    setSubmittingReview(true);
    setReviewError(null);
    try {
      const newReview = await createReview({
        report_id: numericReportId,
        decision,
        comment: comment.trim() || undefined,
        reviewer: user?.name ? `${user.name} (${user.role})` : 'HSE Officer',
      });
      setReviews(prev => [newReview, ...prev]);
      setComment('');
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : 'Failed to submit review decision.');
    } finally {
      setSubmittingReview(false);
    }
  }

  if (!report) return (
    <div className="p-6">
      <button onClick={() => navigate('/app/reports')} className="btn-secondary text-sm mb-4"><ArrowLeft className="w-4 h-4" />Back</button>
      <div className="card text-slate-500">Report not found.</div>
    </div>
  );

  const latestReview = reviews[0];

  return (
    <div className="p-6 max-w-5xl mx-auto animate-in">
      <button onClick={() => navigate('/app/reports')} className="btn-secondary text-sm mb-5"><ArrowLeft className="w-4 h-4" />Back to Reports</button>

      <div className="grid lg:grid-cols-3 gap-5">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-4">
          {/* Report header */}
          <div className="card">
            <div className="flex items-start gap-4 mb-4">
              {analysis && <RiskGauge score={analysis.risk_score} size={90} />}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="text-slate-500 font-mono text-sm">#{report.id}</span>
                  {report.sif_potential && <SIFBadge potential={report.sif_potential} />}
                  {analysis && <RiskBadge level={analysis.risk_level} />}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-slate-500">Type: </span><span className="text-slate-700 font-medium">{report.report_type}</span></div>
                  <div><span className="text-slate-500">Date: </span><span className="text-slate-700 font-medium">{report.date || '—'}</span></div>
                  <div><span className="text-slate-500">Site: </span><span className="text-slate-700 font-medium">{report.site || '—'}</span></div>
                  <div><span className="text-slate-500">Activity: </span><span className="text-slate-700 font-medium">{report.activity || '—'}</span></div>
                  <div><span className="text-slate-500">Location: </span><span className="text-slate-700 font-medium">{report.location || '—'}</span></div>
                </div>
              </div>
            </div>
            <div className="border-t border-slate-200 pt-4">
              <h3 className="text-xs font-semibold text-slate-500 uppercase mb-2">Report Text</h3>
              <p className="text-slate-800 text-sm leading-relaxed">{report.report_text}</p>
            </div>
          </div>

          {/* AI Analysis & Explanation */}
          {analysis && (
            <div className="card space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-600" />Safety Intelligence &amp; AI Analysis
                </h3>
                {explanation ? (
                  explanation.source === 'llm_verified' ? (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
                      LLM Verified
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">
                      Fallback ({explanation.validation_reason || 'rule_based'})
                    </span>
                  )
                ) : loadingExplanation ? (
                  <span className="text-xs text-slate-400 animate-pulse">Analyzing...</span>
                ) : null}
              </div>

              {/* Confidence & Source metadata */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs flex items-center justify-between flex-wrap gap-2">
                <p><span className="text-slate-500">Confidence: </span><strong className="text-slate-800">{analysis.confidence ?? 0.95}</strong></p>
                <p>
                  <span className="text-slate-500">Explanation Source: </span>
                  <strong className="text-slate-800">{explanation?.source || 'rule_engine'}</strong>
                  {explanation?.cached && (
                    <span className="ml-1 px-1.5 py-0.2 bg-blue-100 text-blue-700 rounded text-2xs font-mono font-semibold">cached</span>
                  )}
                </p>
                {explanation?.model_used && explanation.model_used !== 'none' && (
                  <p><span className="text-slate-500">Model: </span><span className="font-mono text-slate-700">{explanation.model_used}</span></p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                  <span className="text-xs text-slate-500 block mb-1">Life-Saving Rule</span>
                  <span className="text-blue-600 font-semibold">{analysis.life_saving_rule}</span>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                  <span className="text-xs text-slate-500 block mb-1">Failed Barrier</span>
                  <span className="text-orange-600 font-semibold">{analysis.barrier_failure}</span>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                  <span className="text-xs text-slate-500 block mb-1">Hazard Detected</span>
                  <span className="text-amber-600 font-semibold">{analysis.hazard_detected}</span>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                  <span className="text-xs text-slate-500 block mb-1">Activity Detected</span>
                  <span className="text-slate-800 font-semibold">{analysis.activity_detected}</span>
                </div>
              </div>

              {/* Evidence */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 mb-2">Key Evidence Phrases</h4>
                <div className="flex flex-wrap gap-2">
                  {analysis.evidence_phrases.map((p, i) => (
                    <span key={i} className="bg-amber-50 border border-amber-200 text-amber-800 px-2.5 py-1 rounded-lg text-xs font-medium">"{p}"</span>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold text-slate-500 mb-2">Explanation</h4>
                <p className="text-slate-700 text-sm leading-relaxed">
                  {explanation ? explanation.risk_explanation : analysis.explanation}
                </p>
                {explanation?.root_cause && (
                  <p className="text-xs text-slate-600 mt-2 italic bg-blue-50/60 p-2.5 rounded border border-blue-100">
                    <strong className="text-blue-900 not-italic">Root Cause: </strong>{explanation.root_cause}
                  </p>
                )}
              </div>

              {/* Structured Evidence & Safety Concepts Panel */}
              <StructuredEvidencePanel
                structuredEvidence={analysis.structured_evidence}
                safetyConcepts={analysis.safety_concepts}
                temporalSequence={analysis.temporal_sequence}
              />

              {/* Five-Factor Explainable Risk Breakdown */}
              <FactorBreakdownView
                factors={analysis.risk_factors}
                breakdown={analysis.factor_breakdown}
              />

              {/* Recommended Actions */}
              <div>
                <h4 className="text-xs font-semibold text-slate-500 mb-2">Recommended Actions</h4>
                <ol className="space-y-1">
                  {((explanation?.recommended_actions || analysis?.recommended_actions || []) as string[]).slice(0, 5).map((a: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-700">
                      <span className="text-blue-600 font-bold flex-shrink-0">{i + 1}.</span>{a}
                    </li>
                  ))}
                </ol>
              </div>

              {/* Debug Panel (Collapsible) */}
              {explanation && (
                <details className="mt-4 p-3 bg-slate-900 text-slate-100 rounded-lg border border-slate-800 text-xs">
                  <summary className="font-semibold text-slate-300 cursor-pointer select-none flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-emerald-400" />
                    Debug Info {explanation.cached ? '(Cached Response)' : '(Live Call)'}
                  </summary>
                  <pre className="mt-2 text-2xs font-mono overflow-x-auto text-emerald-400 p-2.5 bg-slate-950 rounded border border-slate-800">
                    {JSON.stringify(explanation, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}

          {/* Human Review Decision Form */}
          <div className="card border-indigo-100 bg-indigo-50/40">
            <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2 mb-2">
              <MessageSquare className="w-4 h-4 text-indigo-600" />Submit HSE Review Decision
            </h3>
            <p className="text-xs text-slate-500 mb-3">
              AI recommendations support decisions — final verification is recorded in the permanent audit trail.

            </p>

            {latestReview && (
              <div className="mb-3 p-2.5 rounded-lg bg-white border border-indigo-200 text-xs flex items-center justify-between">
                <span className="text-slate-600 font-medium">Latest decision:</span>
                <span className={`px-2.5 py-0.5 rounded-full font-bold border ${
                  DECISION_BADGE[latestReview.decision]?.bg || 'bg-slate-100'
                } ${DECISION_BADGE[latestReview.decision]?.text || 'text-slate-700'} ${DECISION_BADGE[latestReview.decision]?.border || 'border-slate-200'}`}>
                  {latestReview.decision}
                </span>
              </div>
            )}

            {reviewError && (
              <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 text-red-600" />
                <span>{reviewError}</span>
              </div>
            )}

            <textarea
              value={comment}
              onChange={e => setComment(e.target.value)}
              className="input-field text-sm min-h-[70px] resize-none mb-3 bg-white"
              placeholder="Add reviewer notes, rationale, or corrective justification..."
              disabled={submittingReview}
            />

            <div className="flex gap-2.5 flex-wrap">
              <button
                onClick={() => submitReview('CONFIRMED')}
                disabled={submittingReview}
                className="btn-primary text-xs px-3.5 py-2 inline-flex items-center gap-1.5"
              >
                <CheckCircle className="w-4 h-4" />Confirm Finding
              </button>
              <button
                onClick={() => submitReview('CORRECTED')}
                disabled={submittingReview}
                className="btn-secondary text-xs px-3.5 py-2 inline-flex items-center gap-1.5"
              >
                <RotateCcw className="w-4 h-4" />Correct &amp; Adjust
              </button>
              <button
                onClick={() => submitReview('REJECTED')}
                disabled={submittingReview}
                className="btn-danger text-xs px-3.5 py-2 inline-flex items-center gap-1.5"
              >
                <XCircle className="w-4 h-4" />Reject Finding
              </button>
            </div>
          </div>

          {/* Review Audit Trail History */}
          <div className="card space-y-3">
            <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-600" />Review Audit Trail ({reviews.length})
            </h3>

            {loadingReviews ? (
              <p className="text-xs text-slate-500">Loading review history...</p>
            ) : reviews.length === 0 ? (
              <p className="text-xs text-slate-500 py-3">No reviews recorded yet for this report.</p>
            ) : (
              <div className="space-y-2.5 pt-1">
                {reviews.map(rev => {
                  const badge = DECISION_BADGE[rev.decision] || { label: rev.decision, bg: 'bg-slate-100', text: 'text-slate-700', border: 'border-slate-200' };
                  return (
                    <div key={rev.id} className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className={`px-2.5 py-0.5 rounded-full font-bold border ${badge.bg} ${badge.text} ${badge.border}`}>
                          {badge.label}
                        </span>
                        <span className="text-slate-400 font-mono text-2xs">
                          {new Date(rev.created_at).toLocaleString()}
                        </span>
                      </div>
                      {rev.comment && (
                        <p className="text-slate-700 text-xs italic bg-white p-2 rounded border border-slate-100">
                          "{rev.comment}"
                        </p>
                      )}
                      <div className="text-slate-500 text-2xs flex items-center gap-1">
                        <UserIcon className="w-3 h-3 text-slate-400" />
                        Reviewed by: <strong className="text-slate-700">{rev.reviewer}</strong>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Side column */}
        <div className="space-y-4">
          {/* Risk factors */}
          {analysis && (
            <div className="card">
              <h3 className="text-xs font-semibold text-slate-500 uppercase mb-3">Risk Factor Breakdown</h3>
              <div className="space-y-3">
                {analysis.risk_factors.map(f => (
                  <div key={f.name}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-700">{f.name}</span>
                      <span className="text-slate-500 font-medium">{f.score}/{f.max_score}</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-600 rounded-full" style={{ width: `${(f.score / f.max_score) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Similar reports */}
          {similarReports.length > 0 && (
            <div className="card">
              <h3 className="text-xs font-semibold text-slate-500 uppercase mb-3">Similar Reports ({similarReports.length})</h3>
              <div className="space-y-2">
                {similarReports.map(r => (
                  <div key={r.id} className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100/80 transition-colors cursor-pointer" onClick={() => navigate(`/reports/${r.id}`)}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-blue-600 font-mono font-medium">#{r.id}</span>
                      {r.sif_potential && <SIFBadge potential={r.sif_potential} size="sm" />}
                    </div>
                    <p className="text-xs text-slate-600 line-clamp-2">{r.report_text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


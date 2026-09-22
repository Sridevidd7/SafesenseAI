import { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Brain, AlertTriangle, Shield, CheckCircle, Info, Zap,
  ChevronDown, ChevronUp, Sliders, Search, Filter,
  Eye, RefreshCw, ChevronLeft, ChevronRight, Database,
  FileText, Sparkles, Hash, X, ExternalLink
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import {
  fetchReports, analyzeReportApi, fetchReportExplanation,
  ApiReport, LlmExplanationResponse
} from '../services/api';
import { analyzeReport as localAnalyzeReport } from '../utils/riskEngine';
import { ReportAnalysis, SafetyReport, RiskLevel } from '../types';
import RiskGauge from '../components/RiskGauge';
import { RiskBadge, SIFBadge } from '../components/RiskBadge';
import WhatIfSimulator from '../components/WhatIfSimulator';

const PAGE_SIZE = 20;

const EXAMPLE_REPORTS = [
  'Worker entered a confined space without completing required gas testing and permit verification.',
  'Maintenance technician began electrical work on a control panel without applying lockout/tagout. Panel was still energized.',
  'Welding observed in a hazardous area without a valid hot work permit. Flammable vapors were detected nearby.',
  'Worker observed working at 6-meter height without harness or fall-arrest equipment. No edge protection was installed.',
  'Near miss during crane lift: worker walked under suspended load. Exclusion zone had not been established.',
  'Forklift operating in pedestrian walkway without segregation controls. Reversing alarms were not functioning.',
];

export default function AnalysisPage() {
  const { reports: contextReports } = useApp();

  // ─── Input Mode ─────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'explorer' | 'manual'>('explorer');

  // ─── Database Explorer State ───────────────────────────────────────────────
  const [dbReports, setDbReports] = useState<ApiReport[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState<string>('ALL');
  const [page, setPage] = useState(1);
  const [selectedReport, setSelectedReport] = useState<ApiReport | null>(null);

  // ─── Manual Input State ────────────────────────────────────────────────────
  const [manualText, setManualText] = useState('');

  // ─── Modal State ───────────────────────────────────────────────────────────
  const [modalReport, setModalReport] = useState<ApiReport | null>(null);

  // ─── Analysis Output State ─────────────────────────────────────────────────
  const [analysis, setAnalysis] = useState<ReportAnalysis | null>(null);
  const [llmResult, setLlmResult] = useState<LlmExplanationResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzedSource, setAnalyzedSource] = useState<'database' | 'manual' | 'dataset'>('database');
  const [showFactors, setShowFactors] = useState(false);
  const [showSimulator, setShowSimulator] = useState(false);

  // ─── Fetch Database Reports ────────────────────────────────────────────────
  const loadReports = useCallback(async () => {
    setIsLoadingList(true);
    try {
      const res = await fetchReports({
        search: search.trim() || undefined,
        risk_level: riskFilter === 'ALL' ? undefined : riskFilter,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setDbReports(res.reports || []);
      setTotalCount(res.total || 0);
    } catch (err) {
      console.error('Failed to load reports from database:', err);
    } finally {
      setIsLoadingList(false);
    }
  }, [search, riskFilter, page]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Reset to page 1 on filter or search change
  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    setSearch(e.target.value);
    setPage(1);
  }

  function handleFilterChange(level: string) {
    setRiskFilter(level);
    setPage(1);
  }

  // ─── Run Analysis Handler ──────────────────────────────────────────────────
  async function handleAnalyzeReport(report: ApiReport) {
    setSelectedReport(report);
    setAnalyzedSource('database');
    setIsAnalyzing(true);
    setAnalysis(null);
    setLlmResult(null);

    try {
      // 1. Call HSE Rule Engine via Backend API
      let result: ReportAnalysis;
      try {
        result = await analyzeReportApi({
          report_text: report.description,
          severity: report.risk_level,
          life_saving_rule: report.category,
        });
      } catch (err) {
        // Fallback to client-side engine if API unavailable
        result = localAnalyzeReport({
          report_text: report.description,
          severity: report.risk_level,
        });
      }

      setAnalysis(result);

      // 2. Fetch Grounded LLM Explanation with Observability metadata
      try {
        const repId = report.report_id || String(report.id || '');
        const explanation = await fetchReportExplanation(repId);
        if (explanation) {
          setLlmResult(explanation);
        }
      } catch {
        // Observability explanation optional fallback
      }
    } finally {
      setIsAnalyzing(false);
      setShowSimulator(false);
    }
  }

  const [manualInputError, setManualInputError] = useState<string | null>(null);

  async function handleAnalyzeManualText(textToAnalyze?: string) {
    const text = (textToAnalyze ?? manualText).trim();
    if (!text || text.length < 10) {
      setManualInputError("Please provide a detailed safety observation (at least 10 characters).");
      return;
    }
    setManualInputError(null);

    setSelectedReport(null);
    setAnalyzedSource('manual');
    setIsAnalyzing(true);
    setAnalysis(null);
    setLlmResult(null);

    try {
      let result: ReportAnalysis;
      try {
        result = await analyzeReportApi({ report_text: text });
      } catch (err: any) {
        const errorDetail = err?.message || "Analysis request failed";
        if (errorDetail.includes("Please provide a detailed safety observation")) {
          setManualInputError("Please provide a detailed safety observation.");
          return;
        }
        result = localAnalyzeReport({ report_text: text });
      }
      setAnalysis(result);

      try {
        const explanation = await fetchReportExplanation(undefined, {
          description: text,
          life_saving_rule: result.life_saving_rule,
          barrier_failures: result.barrier_failures || [result.barrier_failure],
          risk_score: result.risk_score,
          risk_level: result.risk_level,
          sif_potential: result.sif_potential,
        });
        if (explanation) setLlmResult(explanation);
      } catch {
        // Ignore LLM explanation failure
      }
    } finally {
      setIsAnalyzing(false);
      setShowSimulator(false);
    }
  }


  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <div className="space-y-6 animate-in">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="section-title flex items-center gap-2.5">
            <Brain className="w-7 h-7 text-blue-600" />
            AI Safety Report Analysis
          </h1>
          <p className="section-sub">
            Inspect, classify, and analyze individual safety records stored in the SQLite database or test new observations.
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200 self-start sm:self-auto">
          <button
            onClick={() => setActiveTab('explorer')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'explorer'
                ? 'bg-white text-blue-700 shadow-xs border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            Database Explorer ({totalCount})
          </button>
          <button
            onClick={() => setActiveTab('manual')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'manual'
                ? 'bg-white text-blue-700 shadow-xs border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            Manual Sandbox
          </button>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid lg:grid-cols-12 gap-6 items-start">
        {/* ─── LEFT COLUMN: Explorer Table or Manual Input ─────────────────── */}
        <div className="lg:col-span-7 space-y-4">
          {activeTab === 'explorer' ? (
            <div className="card p-0 overflow-hidden shadow-xs border-slate-200">
              {/* Table Controls Header */}
              <div className="p-4 border-b border-slate-200 bg-slate-50/70 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  {/* Search Bar */}
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input
                      type="text"
                      value={search}
                      onChange={handleSearchChange}
                      placeholder="Search reports by description..."
                      className="input-field pl-9 py-1.5 text-xs w-full bg-white"
                    />
                    {search && (
                      <button
                        onClick={() => { setSearch(''); setPage(1); }}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  {/* Refresh Button */}
                  <button
                    onClick={() => loadReports()}
                    disabled={isLoadingList}
                    className="btn-secondary text-xs py-1.5 px-2.5 flex-shrink-0"
                    title="Refresh records from SQLite database"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isLoadingList ? 'animate-spin text-blue-600' : ''}`} />
                    Refresh
                  </button>
                </div>

                {/* Risk Level Filter Badges */}
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-slate-500 font-semibold mr-1 flex items-center gap-1">
                    <Filter className="w-3 h-3 text-slate-400" /> Filter:
                  </span>
                  {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(lvl => (
                    <button
                      key={lvl}
                      onClick={() => handleFilterChange(lvl)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                        riskFilter === lvl
                          ? 'bg-blue-600 text-white shadow-xs'
                          : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      {lvl}
                    </button>
                  ))}
                </div>
              </div>

              {/* Table Container */}
              <div className="overflow-x-auto min-h-[360px]">
                {isLoadingList ? (
                  <div className="flex flex-col items-center justify-center py-24 text-slate-400">
                    <span className="w-6 h-6 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin mb-2" />
                    <p className="text-xs font-medium">Loading reports from database...</p>
                  </div>
                ) : dbReports.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-center px-4">
                    <Database className="w-10 h-10 text-slate-300 mb-2" />
                    <p className="text-sm font-bold text-slate-700">No matching reports found</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {search ? `Try adjusting search query "${search}"` : 'Upload a dataset to populate records.'}
                    </p>
                  </div>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold select-none">
                      <tr>
                        <th className="py-2.5 px-3 whitespace-nowrap">Report ID</th>
                        <th className="py-2.5 px-3">Description</th>
                        <th className="py-2.5 px-3 whitespace-nowrap">Risk Level</th>
                        <th className="py-2.5 px-3 whitespace-nowrap">Score</th>
                        <th className="py-2.5 px-3 whitespace-nowrap">Date</th>
                        <th className="py-2.5 px-3 whitespace-nowrap text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {dbReports.map(report => {
                        const repId = report.report_id || String(report.id || '');
                        const isSelected = (selectedReport?.report_id || selectedReport?.id) === repId;
                        const dateStr = report.date || (report.created_at ? report.created_at.slice(0, 10) : '—');
                        return (
                          <tr
                            key={repId}
                            onClick={() => setSelectedReport(report)}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? 'bg-blue-50/80 border-l-4 border-l-blue-600'
                                : 'hover:bg-slate-50/80'
                            }`}
                          >
                            {/* Report ID */}
                            <td className="py-3 px-3 align-top whitespace-nowrap">
                              <span className="font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                                {repId.length > 12 ? `${repId.slice(0, 10)}…` : repId}
                              </span>
                            </td>

                            {/* Description & Full Preview */}
                            <td className="py-3 px-3 align-top max-w-[260px]">
                              <p className="text-slate-800 font-medium line-clamp-2 leading-relaxed">
                                {report.description}
                              </p>
                              <div className="flex items-center gap-2 mt-1.5">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setModalReport(report);
                                  }}
                                  className="text-[11px] text-slate-500 hover:text-blue-600 font-medium inline-flex items-center gap-1 underline underline-offset-2"
                                >
                                  <Eye className="w-3 h-3" /> View Full
                                </button>
                                <span className="text-[10px] text-slate-400 font-mono">
                                  {report.category}
                                </span>
                              </div>
                            </td>

                            {/* Risk Level */}
                            <td className="py-3 px-3 align-top whitespace-nowrap">
                              <RiskBadge level={report.risk_level as RiskLevel} size="sm" />
                            </td>

                            {/* Risk Score */}
                            <td className="py-3 px-3 align-top whitespace-nowrap">
                              <span className="font-bold text-slate-700">
                                {report.risk_score}
                              </span>
                              <span className="text-[10px] text-slate-400">/100</span>
                            </td>

                            {/* Date */}
                            <td className="py-3 px-3 align-top whitespace-nowrap text-slate-500 font-mono text-[11px]">
                              {dateStr}
                            </td>

                            {/* Action Analyze Button */}
                            <td className="py-3 px-3 align-top text-right whitespace-nowrap">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAnalyzeReport(report);
                                }}
                                disabled={isAnalyzing && isSelected}
                                className={`text-xs font-semibold px-3 py-1.5 rounded-lg inline-flex items-center gap-1.5 transition-all ${
                                  isSelected
                                    ? 'bg-blue-600 text-white shadow-xs hover:bg-blue-700'
                                    : 'bg-slate-100 text-slate-700 hover:bg-blue-50 hover:text-blue-700 border border-slate-200'
                                }`}
                              >
                                {isAnalyzing && isSelected ? (
                                  <>
                                    <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                    Analyzing...
                                  </>
                                ) : (
                                  <>
                                    <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                                    Analyze
                                  </>
                                )}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Table Pagination Footer */}
              <div className="p-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-600">
                <span className="font-medium">
                  Showing {dbReports.length > 0 ? (page - 1) * PAGE_SIZE + 1 : 0}–
                  {Math.min(page * PAGE_SIZE, totalCount)} of {totalCount} reports
                </span>

                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page <= 1 || isLoadingList}
                    className="p-1 rounded-md border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    title="Previous page"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>

                  <span className="px-2 font-bold text-slate-700">
                    {page} / {totalPages}
                  </span>

                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages || isLoadingList}
                    className="p-1 rounded-md border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    title="Next page"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ) : (
            /* ─── MANUAL INPUT SANDBOX ────────────────────────────────────────── */
            <div className="card space-y-4">
              <div>
                <label className="text-xs font-bold text-slate-800 uppercase tracking-wider block mb-1.5">
                  Enter Safety Observation Text
                </label>
                <textarea
                  value={manualText}
                  onChange={e => {
                    setManualText(e.target.value);
                    if (manualInputError) setManualInputError(null);
                  }}
                  placeholder="Paste or type a safety report observation here..."
                  className={`input-field min-h-[160px] text-sm resize-none ${manualInputError ? 'border-red-400 focus:border-red-500' : ''}`}
                />
                {manualInputError && (
                  <p className="mt-1.5 text-xs font-semibold text-red-600 flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    {manualInputError}
                  </p>
                )}
              </div>


              <div>
                <p className="text-xs font-semibold text-slate-500 mb-2">Quick preset examples:</p>
                <div className="space-y-1.5">
                  {EXAMPLE_REPORTS.map((ex, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        setManualText(ex);
                        handleAnalyzeManualText(ex);
                      }}
                      className="block w-full text-left text-xs text-slate-700 hover:text-blue-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 px-3 py-2 rounded-lg transition-colors truncate"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={() => handleAnalyzeManualText()}
                disabled={!manualText.trim() || isAnalyzing}
                className="btn-primary w-full justify-center py-3 font-bold text-sm"
              >
                {isAnalyzing ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Analyzing observation...
                  </>
                ) : (
                  <>
                    <Brain className="w-4 h-4" />
                    Analyze Observation
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* ─── RIGHT COLUMN: Analysis Results Panel ───────────────────────── */}
        <div className="lg:col-span-5 space-y-5 lg:sticky lg:top-4">
          {!analysis && !isAnalyzing && (
            <div className="card border-dashed border-slate-300 bg-slate-50/60 flex flex-col items-center justify-center py-20 text-center min-h-[420px]">
              <div className="w-16 h-16 rounded-2xl bg-blue-50 border border-blue-100 flex items-center justify-center mb-3">
                <Brain className="w-8 h-8 text-blue-500" />
              </div>
              <p className="text-slate-800 font-bold text-base">Select a Report to Analyze</p>
              <p className="text-slate-500 text-xs mt-1 max-w-xs leading-relaxed">
                Choose any row from the Database Explorer on the left or type a custom scenario in the sandbox.
              </p>
              {selectedReport && (
                <button
                  onClick={() => handleAnalyzeReport(selectedReport)}
                  className="btn-primary mt-4 text-xs"
                >
                  <Sparkles className="w-3.5 h-3.5" /> Analyze Report #{selectedReport.id}
                </button>
              )}
            </div>
          )}

          {/* Loading Animation Card */}
          {isAnalyzing && (
            <div className="card border-blue-200 bg-blue-50/50 p-6 space-y-3">
              <div className="flex items-center gap-3 mb-2">
                <span className="w-5 h-5 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
                <h4 className="font-bold text-sm text-slate-900">Executing HSE Intelligence Analysis</h4>
              </div>
              {['Parsing safety observation tokens...', 'Evaluating Life-Saving Rule (LSR) criteria...', 'Classifying barrier failure modes...', 'Calculating risk severity and SIF probability...', 'Grounding deterministic explanation...'].map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                  {step}
                </div>
              ))}
            </div>
          )}

          {/* Result Card */}
          {analysis && !isAnalyzing && (
            <div className="space-y-4 animate-in fade-in">
              {/* Header Badge */}
              <div className="card p-4 border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">
                      {analyzedSource === 'database' ? `Report #${selectedReport?.id}` : 'Observation Analysis'}
                    </span>
                    <span className="text-[10px] bg-slate-100 text-slate-600 font-semibold px-2 py-0.5 rounded-full border border-slate-200">
                      {analyzedSource === 'database' ? 'Source: SQLite DB' : 'Source: Manual Sandbox'}
                    </span>
                  </div>

                  {llmResult && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border flex items-center gap-1 ${
                      llmResult.source === 'llm_verified'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}>
                      <Sparkles className="w-2.5 h-2.5" />
                      {llmResult.source === 'llm_verified' ? 'LLM Verified' : 'Rule-Based Fallback'}
                    </span>
                  )}
                </div>

                {/* Score & Badges */}
                <div className="flex items-start gap-4">
                  <RiskGauge score={analysis.risk_score} size={90} />
                  <div className="flex-1 space-y-2">
                    <div className="flex flex-wrap gap-1.5">
                      <RiskBadge level={analysis.risk_level} size="md" />
                      <SIFBadge potential={analysis.sif_potential} size="md" />
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-slate-400 text-[10px] font-bold uppercase block">Life-Saving Rule</span>
                        <span className="text-blue-700 font-bold">{analysis.life_saving_rule || 'General Safety'}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 text-[10px] font-bold uppercase block">Failed Barrier</span>
                        <span className="text-orange-700 font-bold">{analysis.barrier_failure || 'Multiple/Unspecified'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Fallback Visibility Banner */}
              {analysis.source === 'fallback' && (
                <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-xs text-amber-900 flex items-start gap-2.5 shadow-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold text-amber-900">Limited analysis due to unclear input</p>
                    <p className="text-[11px] text-amber-700 mt-0.5">
                      {analysis.explanation || 'Uncertain or ambiguous phrasing detected. Manual supervisor verification required.'}
                    </p>
                  </div>
                </div>
              )}

              {/* Input Quality Feedback Banner */}
              {analysis.input_feedback && (
                <div className={`p-2.5 rounded-xl text-xs flex items-center gap-2 border shadow-xs ${
                  analysis.analysis_quality === 'LOW'
                    ? 'bg-orange-50 border-orange-200 text-orange-800'
                    : analysis.analysis_quality === 'MEDIUM'
                    ? 'bg-blue-50 border-blue-200 text-blue-800'
                    : 'bg-emerald-50 border-emerald-200 text-emerald-800'
                }`}>
                  <Info className="w-3.5 h-3.5 shrink-0" />
                  <span><strong>Input Quality:</strong> {analysis.input_feedback}</span>
                </div>
              )}

              {/* AI Confidence Explanation Card */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                    AI Confidence Assessment
                  </span>
                  <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-md border ${
                    analysis.system_confidence === 'HIGH'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : analysis.system_confidence === 'MEDIUM'
                      ? 'bg-blue-50 text-blue-700 border-blue-200'
                      : 'bg-amber-50 text-amber-700 border-amber-200'
                  }`}>
                    {analysis.system_confidence || 'HIGH'}
                  </span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {analysis.confidence_reason_user || "High confidence because multiple strong safety violations and clear action words were detected."}
                </p>
              </div>

              {/* Grounded Explanation */}
              <div className="card p-4 space-y-2.5">
                <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                  <Zap className="w-3.5 h-3.5 text-amber-500" />
                  Root Cause &amp; Risk Explanation
                </h4>


                {analysis.evidence_phrases && analysis.evidence_phrases.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-1">
                    {analysis.evidence_phrases.map((phrase, idx) => (
                      <span key={idx} className="bg-amber-50 border border-amber-200 text-amber-900 text-[10px] font-semibold px-2 py-0.5 rounded">
                        ✓ "{phrase}"
                      </span>
                    ))}
                  </div>
                )}

                <p className="text-xs text-slate-700 leading-relaxed">
                  {llmResult?.risk_explanation || analysis.explanation}
                </p>
              </div>

              {/* Recommended Actions */}
              {analysis.recommended_actions && analysis.recommended_actions.length > 0 && (
                <div className="card p-4 space-y-2">
                  <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                    <CheckCircle className="w-3.5 h-3.5 text-green-600" />
                    Recommended Corrective Actions
                  </h4>
                  <ul className="space-y-1.5">
                    {analysis.recommended_actions.slice(0, 4).map((act, i) => (
                      <li key={i} className="text-xs text-slate-700 flex items-start gap-2">
                        <span className="text-blue-600 font-bold text-[10px] mt-0.5">•</span>
                        <span>{act}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Risk Factor Breakdown Accordion */}
              {analysis.risk_factors && analysis.risk_factors.length > 0 && (
                <div className="card p-4">
                  <button
                    onClick={() => setShowFactors(!showFactors)}
                    className="flex items-center justify-between w-full text-xs font-bold text-slate-800"
                  >
                    <span className="flex items-center gap-1.5">
                      <Sliders className="w-3.5 h-3.5 text-blue-600" />
                      Risk Factor Breakdown ({analysis.risk_factors.length})
                    </span>
                    {showFactors ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>

                  {showFactors && (
                    <div className="mt-3 space-y-2.5 pt-2 border-t border-slate-100">
                      {analysis.risk_factors.map(f => (
                        <div key={f.name} className="text-xs">
                          <div className="flex justify-between text-[11px] mb-1">
                            <span className="font-semibold text-slate-700">{f.name}</span>
                            <span className="font-bold text-slate-500">{f.score}/{f.max_score}</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-600 rounded-full"
                              style={{ width: `${(f.score / f.max_score) * 100}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Simulator Toggle */}
              <button
                onClick={() => setShowSimulator(!showSimulator)}
                className="btn-secondary w-full justify-center text-xs py-2"
              >
                <Sliders className="w-3.5 h-3.5 text-blue-600" />
                {showSimulator ? 'Close Safety Control Simulator' : 'Open Safety Control Simulator'}
              </button>

              {showSimulator && (
                <WhatIfSimulator
                  originalScore={analysis.risk_score}
                  activity={analysis.activity_detected}
                  lsr={analysis.life_saving_rule}
                />
              )}
            </div>
          )}
        </div>
      </div>

      {/* ─── FULL DESCRIPTION MODAL ────────────────────────────────────────── */}
      {modalReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold text-sm text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded-md border border-blue-100">
                  Report #{modalReport.id}
                </span>
                <span className="text-xs text-slate-400">
                  {modalReport.created_at ? new Date(modalReport.created_at).toLocaleString() : ''}
                </span>
              </div>
              <button
                onClick={() => setModalReport(null)}
                className="text-slate-400 hover:text-slate-700 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Full Observation</span>
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 leading-relaxed max-h-60 overflow-y-auto font-sans">
                {modalReport.description}
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-semibold">Category</span>
                <span className="font-bold text-slate-800">{modalReport.category}</span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-semibold">Risk Level</span>
                <span className="font-bold text-slate-800">{modalReport.risk_level} ({modalReport.risk_score}/100)</span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-semibold">SIF Potential</span>
                <span className="font-bold text-slate-800">{modalReport.sif_potential}</span>
              </div>
            </div>

            {modalReport.report_id && (
              <div className="text-[11px] text-slate-500 bg-slate-50 px-3 py-1.5 rounded-lg font-mono flex items-center gap-1.5 border border-slate-100">
                <Hash className="w-3.5 h-3.5 text-slate-400" />
                <span className="truncate">Report ID: {modalReport.report_id}</span>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setModalReport(null)} className="btn-secondary text-xs">
                Close
              </button>
              <button
                onClick={() => {
                  const r = modalReport;
                  setModalReport(null);
                  handleAnalyzeReport(r);
                }}
                className="btn-primary text-xs"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Analyze This Report
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

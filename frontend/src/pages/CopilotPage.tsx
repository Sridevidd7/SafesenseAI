import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare, Send, Bot, User, Database, Shield,
  AlertCircle, Cpu, ExternalLink, Sparkles, ChevronDown, ChevronUp, Filter,
  CheckCircle2, Loader2, ShieldCheck, Square
} from 'lucide-react';
import { CopilotMessage, CopilotGrounding } from '../types';
import { sendCopilotMessage, CopilotHistoryMessage } from '../services/api';
import { streamCopilotChat, CopilotStageId } from '../services/streamClient';
import { fetchPlatformInfo, PlatformInfo, getStoredToken, clearStoredSession } from '../services/authClient';

const SUGGESTED_QUESTIONS = [
  "What is the biggest safety risk in the dataset?",
  "Which site has the most SIF potential reports?",
  "Show all high-risk confined space reports.",
  "What is the most common failed safety barrier?",
  "Which life-saving rule appears most often?",
  "What changed in the last 30 days?",
  "How many critical reports are there?",
  "What are the top recurring safety patterns?",
];

/**
 * Display order for Copilot workflow stages. Mirrors the backend pipeline
 * (backend/routes/copilot.py). Actual progress is driven ONLY by real backend
 * SSE events — a stage is never marked active/done speculatively.
 */
const STAGE_ORDER: Array<{ id: CopilotStageId; label: string }> = [
  { id: 'SANITIZE', label: 'Protecting sensitive information' },
  { id: 'UNDERSTAND', label: 'Understanding your question' },
  { id: 'RETRIEVE', label: 'Searching verified safety reports' },
  { id: 'SIF_ANALYSIS', label: 'Checking SIF precursor evidence' },
  { id: 'BARRIER_ANALYSIS', label: 'Checking failed safety barriers' },
  { id: 'PATTERN_ANALYSIS', label: 'Checking recurring safety patterns' },
  { id: 'EVIDENCE', label: 'Building grounded evidence' },
  { id: 'GENERATION', label: 'Generating grounded response' },
];

interface StageRun {
  status: 'active' | 'done';
  duration_ms?: number;
}

type StageRunMap = Partial<Record<CopilotStageId, StageRun>>;

function stageRunProgress(runs: StageRunMap): { done: number; active: CopilotStageId | null } {
  let done = 0;
  let active: CopilotStageId | null = null;
  for (const { id } of STAGE_ORDER) {
    const run = runs[id];
    if (run?.status === 'done') done += 1;
    else if (run?.status === 'active' && !active) active = id;
  }
  return { done, active };
}

/** Live workflow timeline — reflects real backend stage events only. */
function StageTimeline({ runs }: { runs: StageRunMap }) {
  const { done, active } = stageRunProgress(runs);
  const progressPct = Math.round((done / STAGE_ORDER.length) * 100);
  const activeLabel = STAGE_ORDER.find(s => s.id === active)?.label;

  return (
    <div
      className="w-full rounded-lg border border-blue-100 bg-blue-50/40 px-3.5 py-3 space-y-2"
      role="status"
      aria-label="Safety Copilot workflow progress"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-blue-700">
          Copilot workflow
        </span>
        <span className="text-[10px] font-mono text-blue-500">{progressPct}%</span>
      </div>
      <div className="h-1 rounded-full bg-blue-100 overflow-hidden" aria-hidden="true">
        <div
          className="h-full bg-blue-600 rounded-full transition-all duration-500"
          style={{ width: `${Math.max(progressPct, 4)}%` }}
        />
      </div>
      <ol className="space-y-1.5 pt-1">
        {STAGE_ORDER.map(({ id, label }) => {
          const run = runs[id];
          const isDone = run?.status === 'done';
          const isActive = run?.status === 'active';
          return (
            <li key={id} className={`flex items-center gap-2 text-xs ${isActive ? 'text-slate-800 font-medium' : isDone ? 'text-slate-500' : 'text-slate-400'}`}>
              {isDone ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" aria-hidden="true" />
              ) : isActive ? (
                <Loader2 className="w-3.5 h-3.5 text-blue-600 shrink-0 animate-spin" aria-hidden="true" />
              ) : (
                <span className="w-3.5 h-3.5 shrink-0 rounded-full border border-slate-300" aria-hidden="true" />
              )}
              <span>{label}</span>
              {isDone && typeof run?.duration_ms === 'number' && (
                <span className="text-[10px] font-mono text-slate-400 ml-auto">{run.duration_ms}ms</span>
              )}
              {isActive && (
                <span className="ml-auto flex items-center gap-1 text-[10px] font-semibold text-blue-600">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" aria-hidden="true" />
                  running
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {/* Accessible live region — announces stage transitions to screen readers */}
      <div aria-live="polite" className="sr-only">
        {activeLabel ? `Copilot: ${activeLabel}` : 'Copilot workflow complete'}
      </div>
    </div>
  );
}

/** Compact deterministic-evidence panel rendered under each grounded answer. */
function GroundingPanel({ grounding, sourceLabel }: { grounding: CopilotGrounding; sourceLabel: string }) {
  const filterEntries = Object.entries(grounding.filters_applied || {});
  return (
    <div className="w-full rounded-lg border border-slate-200 bg-white/70 px-3 py-2 space-y-1.5">
      <div className="flex items-center gap-1.5 flex-wrap">
        <Database className="w-3.5 h-3.5 text-emerald-600" />
        <span className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Evidence</span>
        <span className="text-xs text-slate-600">
          {grounding.reports_examined} report{grounding.reports_examined === 1 ? '' : 's'} examined
          {' \u00b7 '}{grounding.sif_count} SIF-potential
          {grounding.date_range ? ` \u00b7 ${grounding.date_range}` : ''}
        </span>
        <span
          className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded-full"
          title={`Deterministic retrieval from ${sourceLabel}`}
        >
          <ShieldCheck className="w-3 h-3" aria-hidden="true" />
          Grounded in verified SafeSense data
        </span>
      </div>
      {filterEntries.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <Filter className="w-3 h-3 text-slate-400" />
          {filterEntries.map(([k, v]) => (
            <span key={k} className="text-[11px] bg-slate-100 text-slate-600 border border-slate-200 px-1.5 py-0.5 rounded font-mono">
              {k}: {v}
            </span>
          ))}
        </div>
      )}
      {grounding.aggregates?.filter(a => a.metric.startsWith('barrier_frequency:')).length > 0 && (
        <div className="text-[11px] text-slate-500">
          <span className="font-semibold text-slate-600">Barrier frequency:</span>{' '}
          {grounding.aggregates
            .filter(a => a.metric.startsWith('barrier_frequency:'))
            .map(a => `${a.metric.replace('barrier_frequency:', '')} (${a.value})`)
            .join(' \u00b7 ')}
        </div>
      )}
      {grounding.patterns && grounding.patterns.length > 0 && (
        <div className="text-[11px] text-slate-500">
          <span className="font-semibold text-slate-600">Patterns ({grounding.pattern_source}):</span>{' '}
          {grounding.patterns.map(p => `${p.pattern_id} \u2014 ${p.description} (${p.frequency} reports)`).join(' \u00b7 ')}
        </div>
      )}
      {grounding.filters_unapplied && grounding.filters_unapplied.length > 0 && (
        <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">
          Filters not applied: {grounding.filters_unapplied.join('; ')}
        </div>
      )}
    </div>
  );
}

export default function CopilotPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<CopilotMessage[]>([
    {
      id: '0',
      role: 'assistant',
      content: `Hello! I'm the **SafeSense Safety Copilot**, an AI-powered HSE intelligence assistant.\n\nI query our verified safety database to deliver grounded answers, identify barrier failures, and assess SIF potential across operating sites.\n\n*All responses are strictly grounded in our database with report citations.*`,
      timestamp: new Date().toISOString(),
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamActive, setStreamActive] = useState(false);
  const [stageRuns, setStageRuns] = useState<StageRunMap>({});
  const [streamedText, setStreamedText] = useState('');
  const [platformInfo, setPlatformInfo] = useState<PlatformInfo | null>(null);
  const [dataSourceLabel, setDataSourceLabel] = useState<string | null>(null);
  const [showMobileQuestions, setShowMobileQuestions] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Dynamic platform label from backend metadata — never hardcoded.
    fetchPlatformInfo().then(info => {
      if (info) setPlatformInfo(info);
    });
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamedText, stageRuns, loading]);

  const sourceDisplay = dataSourceLabel ?? platformInfo?.database ?? 'Verified SafeSense Database';

  function handleAuthExpired() {
    clearStoredSession();
    navigate('/login?expired=1');
  }

  function resetStreamState() {
    setStageRuns({});
    setStreamedText('');
    setStreamActive(false);
    abortRef.current = null;
  }

  async function runStreamingRequest(trimmed: string, history: CopilotHistoryMessage[]): Promise<boolean> {
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamCopilotChat(
        { message: trimmed, history },
        {
          signal: controller.signal,
          onEvent: ev => {
            // First real event from the backend proves the stream is live —
            // only then do we swap the fallback spinner for the timeline.
            setStreamActive(true);
            switch (ev.type) {
              case 'stage':
                if (ev.stage) {
                  setStageRuns(prev => ({ ...prev, [ev.stage as CopilotStageId]: { status: 'active' } }));
                }
                break;
              case 'stage_done':
                if (ev.stage) {
                  setStageRuns(prev => ({
                    ...prev,
                    [ev.stage as CopilotStageId]: { status: 'done', duration_ms: ev.duration_ms },
                  }));
                }
                break;
              case 'token':
                if (ev.content) setStreamedText(prev => prev + ev.content);
                break;
              case 'complete': {
                if (ev.data_source) setDataSourceLabel(ev.data_source);
                const assistantMsg: CopilotMessage = {
                  id: (Date.now() + 1).toString(),
                  role: 'assistant',
                  content: ev.answer ?? '',
                  timestamp: new Date().toISOString(),
                  source_reports: ev.source_reports,
                  model: ev.model,
                  grounding: (ev.grounding as unknown as CopilotGrounding) ?? undefined,
                };
                setMessages(prev => [...prev, assistantMsg]);
                break;
              }
              case 'error':
                // The stream transport works; the backend reported an app-level
                // problem (e.g. missing LLM key). The notice is already shown —
                // do NOT retry via the blocking endpoint (would duplicate it).
                setMessages(prev => [
                  ...prev,
                  {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: `**Safety Copilot Notice:**\n\n${ev.message || 'The Copilot could not complete this request.'}`,
                    timestamp: new Date().toISOString(),
                    isError: true,
                  },
                ]);
                break;
            }
          },
        },
      );
      // true = handled (complete, aborted, 401 handled, or error event shown).
      // false = stream transport unavailable → caller falls back to blocking.
      return true;
    } catch (err: any) {
      if (err?.name === 'AbortError') return true; // user cancelled — not an error
      if (err?.status === 401) {
        handleAuthExpired();
        return true;
      }
      // Streaming endpoint unavailable (404/proxy issues) → caller falls back
      return false;
    }
  }

  async function runBlockingRequest(trimmed: string, history: CopilotHistoryMessage[]) {
    try {
      const res = await sendCopilotMessage({ message: trimmed, history });
      const assistantMsg: CopilotMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.answer,
        timestamp: new Date().toISOString(),
        source_reports: res.source_reports,
        model: res.model,
        grounding: res.grounding ?? undefined,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      if (err?.status === 401) {
        handleAuthExpired();
        return;
      }
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: `**Safety Copilot Notice:**\n\n${err?.message || 'Unable to connect to the Safety Copilot service.'}`,
          timestamp: new Date().toISOString(),
          isError: true,
        },
      ]);
    }
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg: CopilotMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setStageRuns({});
    setStreamedText('');

    // Build conversation history excluding intro and error notices
    const history: CopilotHistoryMessage[] = messages
      .filter(m => m.id !== '0' && !m.isError)
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }));

    // Preferred path: real SSE streaming. Falls back to the blocking endpoint
    // only when the stream transport itself is unavailable.
    const streamed = await runStreamingRequest(trimmed, history);
    if (!streamed) {
      await runBlockingRequest(trimmed, history);
    }
    resetStreamState();
    setLoading(false);
  }

  function stopStreaming() {
    abortRef.current?.abort();
  }

  function renderContent(text: string) {
    return text.split('\n').map((line, i) => {
      // Bold text formatting
      let formatted = line.replace(/\*\*(.+?)\*\*/g, '<strong class="font-bold text-slate-900">$1</strong>');
      // Highlight report citations like [Report XYZ]
      formatted = formatted.replace(
        /\[Report\s+([^\]]+)\]/gi,
        '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-medium bg-blue-50 text-blue-700 border border-blue-200 shadow-2xs">Report $1</span>'
      );
      return (
        <p
          key={i}
          className="text-xs sm:text-sm text-slate-700 leading-relaxed mb-1"
          dangerouslySetInnerHTML={{ __html: formatted || '&nbsp;' }}
        />
      );
    });
  }

  return (
    <div className="h-[calc(100vh-8.5rem)] flex flex-col space-y-3.5 animate-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="section-title flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-blue-600" />
            Safety Copilot
          </h1>
          <p className="section-sub mb-0">
            Evidence-first AI reasoning over your safety database: deterministic retrieval, grounded answers, PII-sanitized &amp; cite-verified.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto px-3 py-1.5 bg-slate-100 rounded-lg text-xs font-medium text-slate-600 border border-slate-200 shadow-2xs">
          <Cpu className="w-3.5 h-3.5 text-blue-600 shrink-0" aria-hidden="true" />
          <span className="hidden sm:inline">Engine: Groq LLM</span>
          <span className="text-slate-300 hidden sm:inline">|</span>
          <Database className="w-3.5 h-3.5 text-emerald-600 shrink-0" aria-hidden="true" />
          <span>{sourceDisplay} · Verified Safety Database</span>
        </div>
      </div>

      {/* Mobile Suggested Questions Toggle */}
      <div className="md:hidden">
        <button
          onClick={() => setShowMobileQuestions(!showMobileQuestions)}
          className="w-full btn-secondary text-xs flex items-center justify-between py-2 px-3"
          aria-expanded={showMobileQuestions}
        >
          <span className="flex items-center gap-1.5 font-bold text-slate-700">
            <Sparkles className="w-3.5 h-3.5 text-blue-600" />
            Suggested Questions ({SUGGESTED_QUESTIONS.length})
          </span>
          {showMobileQuestions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showMobileQuestions && (
          <div className="mt-2 p-3 bg-white border border-slate-200 rounded-xl space-y-1.5 shadow-sm max-h-48 overflow-y-auto">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => {
                  sendMessage(q);
                  setShowMobileQuestions(false);
                }}
                disabled={loading}
                className="w-full text-left text-xs text-slate-700 hover:text-blue-700 bg-slate-50 hover:bg-blue-50 border border-slate-200 p-2 rounded-lg transition-colors truncate"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 flex gap-4 min-h-0">
        {/* Chat Area */}
        <div className="flex-1 flex flex-col bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : msg.isError
                      ? 'bg-amber-100 text-amber-700 border border-amber-300'
                      : 'bg-slate-900 text-white'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <User className="w-4 h-4" />
                  ) : msg.isError ? (
                    <AlertCircle className="w-4 h-4" />
                  ) : (
                    <Bot className="w-4 h-4" />
                  )}
                </div>

                <div className={`max-w-[85%] sm:max-w-[80%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1.5`}>
                  <div
                    className={`rounded-2xl px-4 py-3 shadow-2xs ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-tr-xs'
                        : msg.isError
                        ? 'bg-amber-50/80 border border-amber-200 text-amber-900 rounded-tl-xs'
                        : 'bg-slate-50 border border-slate-200 rounded-tl-xs'
                    }`}
                  >
                    {msg.role === 'user' ? (
                      <p className="text-xs sm:text-sm leading-relaxed">{msg.content}</p>
                    ) : (
                      <div className="space-y-1">{renderContent(msg.content)}</div>
                    )}
                  </div>
                  {msg.grounding ? (
                    <GroundingPanel grounding={msg.grounding} sourceLabel={sourceDisplay} />
                  ) : msg.source_reports && msg.source_reports.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Database className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="text-[11px] text-slate-500 font-medium">Grounded in reports:</span>
                      {msg.source_reports.map(id => (
                        <button
                          key={id}
                          onClick={() => navigate(`/reports/${id}`)}
                          className="text-[11px] bg-slate-100 hover:bg-blue-50 text-slate-700 hover:text-blue-700 border border-slate-200 px-1.5 py-0.5 rounded font-mono font-semibold transition-colors inline-flex items-center gap-1"
                          title={`Inspect report ${id}`}
                        >
                          <span>#{id}</span>
                          <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                        </button>
                      ))}
                    </div>
                  )}

                  {msg.model && (
                    <span className="text-[10px] text-slate-400 font-mono">
                      model: {msg.model}
                    </span>
                  )}
                </div>
              </div>
            ))}

            {/* Real-time streaming block: live stage timeline + streamed answer */}
            {loading && streamActive && (
              <div className="flex gap-3 animate-in fade-in">
                <div className="w-8 h-8 rounded-full bg-slate-900 text-white flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="flex-1 max-w-[85%] sm:max-w-[80%] space-y-2">
                  <StageTimeline runs={stageRuns} />
                  {streamedText && (
                    <div className="bg-slate-50 border border-slate-200 rounded-2xl rounded-tl-xs px-4 py-3 shadow-2xs">
                      <div className="space-y-1">
                        {renderContent(streamedText)}
                        <span
                          className="inline-block w-2 h-3.5 bg-blue-600 animate-pulse align-middle rounded-[1px]"
                          aria-hidden="true"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Fallback spinner (blocking endpoint) */}
            {loading && !streamActive && (
              <div className="flex gap-3 animate-in fade-in">
                <div className="w-8 h-8 rounded-full bg-slate-900 text-white flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-2xl rounded-tl-xs px-4 py-3 flex items-center gap-2.5 shadow-2xs">
                  <span className="w-3.5 h-3.5 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
                  <span className="text-xs sm:text-sm text-slate-600 font-medium">
                    Retrieving verified safety context &amp; reasoning via Groq...
                  </span>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input Box */}
          <div className="border-t border-slate-200 p-3 bg-slate-50/60">
            <div className="flex gap-2">
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage(input)}
                className="input-field flex-1 text-xs sm:text-sm bg-white"
                placeholder="Ask about high-risk sites, recurring barriers, SIF precursors, or specific controls..."
                disabled={loading}
                aria-label="Ask the Safety Copilot a question"
              />
              {streamActive ? (
                <button
                  onClick={stopStreaming}
                  className="btn-secondary px-4 text-xs font-bold text-red-600 border-red-200 hover:bg-red-50"
                  aria-label="Stop generating response"
                  title="Stop generating"
                >
                  <Square className="w-3.5 h-3.5" />
                </button>
              ) : (
                <button
                  onClick={() => sendMessage(input)}
                  disabled={!input.trim() || loading}
                  className="btn-primary px-4 text-xs font-bold"
                  aria-label="Send question to Safety Copilot"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Suggested Questions Sidebar (Desktop) */}
        <div className="w-64 flex-shrink-0 hidden md:block">
          <div className="card h-full flex flex-col justify-between p-4 bg-white border-slate-200">
            <div>
              <div className="flex items-center gap-1.5 mb-3">
                <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Suggested Inquiries
                </h3>
              </div>
              <div className="space-y-1.5">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(q)}
                    disabled={loading}
                    className="w-full text-left text-xs font-medium text-slate-700 hover:text-blue-700 bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-200 p-2.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-3 border-t border-slate-200 space-y-2">
              <div className="flex items-center gap-1.5 text-[10px] font-semibold text-emerald-700">
                <ShieldCheck className="w-3.5 h-3.5" />
                Grounded in verified SafeSense data
              </div>
              <div className="flex items-start gap-2 text-[11px] text-slate-500 leading-relaxed">
                <Shield className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                <span>
                  SafeSense Copilot grounds answers on verified database records. Operational decisions require HSE officer authorization.
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Bot, User, Database, Shield, AlertCircle, Cpu, Filter } from 'lucide-react';
import { CopilotMessage, CopilotGrounding } from '../types';
import { sendCopilotMessage, CopilotHistoryMessage } from '../services/api';

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

/** Compact deterministic-evidence panel rendered under each grounded answer. */
function GroundingPanel({ grounding }: { grounding: CopilotGrounding }) {
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
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

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

    try {
      // Build conversation history excluding intro and error notices
      const history: CopilotHistoryMessage[] = messages
        .filter(m => m.id !== '0' && !m.isError)
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      const res = await sendCopilotMessage({
        message: trimmed,
        history,
      });

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
      const errorMsg: CopilotMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `**Safety Copilot Notice:**\n\n${err?.message || 'Unable to connect to the Safety Copilot service.'}\n\n*Please ensure GROQ_API_KEY is configured in your backend environment (.env) to enable full AI reasoning.*`,
        timestamp: new Date().toISOString(),
        isError: true,
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }

  function renderContent(text: string) {
    return text.split('\n').map((line, i) => {
      // Bold text formatting
      let formatted = line.replace(/\*\*(.+?)\*\*/g, '<strong class="font-bold text-slate-900">$1</strong>');
      // Highlight report citations like [Report XYZ]
      formatted = formatted.replace(
        /\[Report\s+([^\]]+)\]/gi,
        '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-medium bg-blue-50 text-blue-700 border border-blue-200">Report $1</span>'
      );
      return (
        <p
          key={i}
          className="text-sm text-slate-700 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: formatted || '&nbsp;' }}
        />
      );
    });
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col space-y-4 animate-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="section-title flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-blue-600" />
            Safety Copilot
          </h1>
          <p className="section-sub mb-0">
            Evidence-first AI reasoning over your safety database: deterministic retrieval, grounded answers, PII-sanitized & cite-verified.
          </p>
        </div>
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-100 rounded-lg text-xs font-medium text-slate-600 border border-slate-200">
          <Cpu className="w-3.5 h-3.5 text-blue-600" />
          <span>Engine: Groq Llama 3.3 70B</span>
          <span className="text-slate-300">|</span>
          <Database className="w-3.5 h-3.5 text-emerald-600" />
          <span>Source: SQLite</span>
        </div>
      </div>

      <div className="flex-1 flex gap-5 min-h-0">
        {/* Chat area */}
        <div className="flex-1 flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  msg.role === 'user'
                    ? 'bg-slate-200 text-slate-700'
                    : msg.isError
                    ? 'bg-amber-100 text-amber-700 border border-amber-300'
                    : 'bg-blue-600 text-white'
                }`}>
                  {msg.role === 'user' ? (
                    <User className="w-4 h-4" />
                  ) : msg.isError ? (
                    <AlertCircle className="w-4 h-4" />
                  ) : (
                    <Bot className="w-4 h-4" />
                  )}
                </div>
                <div className={`max-w-[80%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1.5`}>
                  <div className={`rounded-xl px-4 py-3 shadow-xs ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : msg.isError
                      ? 'bg-amber-50/70 border border-amber-200 text-amber-900'
                      : 'bg-slate-50 border border-slate-200'
                  }`}>
                    {msg.role === 'user' ? (
                      <p className="text-sm leading-relaxed">{msg.content}</p>
                    ) : (
                      <div className="space-y-1">{renderContent(msg.content)}</div>
                    )}
                  </div>
                  {msg.grounding ? (
                    <GroundingPanel grounding={msg.grounding} />
                  ) : msg.source_reports && msg.source_reports.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Database className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-xs text-slate-500 font-medium">Source reports retrieved:</span>
                      {msg.source_reports.map(id => (
                        <span
                          key={id}
                          className="text-xs bg-slate-100 text-slate-600 border border-slate-200 px-1.5 py-0.5 rounded font-mono font-medium"
                        >
                          {id}
                        </span>
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
            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 flex items-center gap-2.5">
                  <span className="w-3.5 h-3.5 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
                  <span className="text-sm text-slate-600 font-medium">
                    Retrieving database context & reasoning via Groq...
                  </span>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <div className="border-t border-slate-200 p-3.5 bg-slate-50/50">
            <div className="flex gap-2.5">
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage(input)}
                className="input-field flex-1 text-sm bg-white"
                placeholder="Ask about high-risk sites, barrier failures, SIF potential, or activities..."
                disabled={loading}
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || loading}
                className="btn-primary px-4"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Suggested questions sidebar */}
        <div className="w-64 flex-shrink-0 hidden md:block">
          <div className="card h-full flex flex-col justify-between p-5">
            <div>
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                Suggested Questions
              </h3>
              <div className="space-y-2">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(q)}
                    disabled={loading}
                    className="w-full text-left text-xs font-medium text-slate-700 hover:text-blue-700 bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-200 p-2.5 rounded-lg transition-all disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
            <div className="pt-4 border-t border-slate-200">
              <div className="flex items-start gap-2 text-xs text-slate-500 leading-relaxed">
                <Shield className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
                AI supports HSE decision-making. Final decisions remain with authorized safety personnel.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare, Send, Bot, User, Database, Shield,
  AlertCircle, Cpu, ExternalLink, Sparkles, ChevronDown, ChevronUp
} from 'lucide-react';
import { CopilotMessage } from '../types';
import { sendCopilotMessage, CopilotHistoryMessage } from '../services/api';

const SUGGESTED_QUESTIONS = [
  "What is the biggest safety risk in the dataset?",
  "Which site has the most SIF potential reports?",
  "Show all high-risk confined space reports.",
  "What is the most common failed safety barrier?",
  "Which life-saving rule appears most often?",
  "Which activity is showing the highest risk?",
  "How many critical reports are there?",
  "What are the top recurring safety patterns?",
];

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
  const [showMobileQuestions, setShowMobileQuestions] = useState(false);
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
            Real-time grounded AI reasoning across your safety database. PII-sanitized &amp; cite-verified.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto px-3 py-1.5 bg-slate-100 rounded-lg text-xs font-medium text-slate-600 border border-slate-200 shadow-2xs">
          <Cpu className="w-3.5 h-3.5 text-blue-600 shrink-0" />
          <span className="hidden sm:inline">Engine: Groq Llama 3.3 70B</span>
          <span className="text-slate-300 hidden sm:inline">|</span>
          <Database className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
          <span>Source: SQLite Database</span>
        </div>
      </div>

      {/* Mobile Suggested Questions Toggle */}
      <div className="md:hidden">
        <button
          onClick={() => setShowMobileQuestions(!showMobileQuestions)}
          className="w-full btn-secondary text-xs flex items-center justify-between py-2 px-3"
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

                  {/* Grounded Source Citations */}
                  {msg.source_reports && msg.source_reports.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
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

            {loading && (
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
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || loading}
                className="btn-primary px-4 text-xs font-bold"
                aria-label="Send question to Safety Copilot"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
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

            <div className="pt-3 border-t border-slate-200">
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

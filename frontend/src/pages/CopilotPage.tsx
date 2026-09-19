import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Bot, User, Database, Shield } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { CopilotMessage } from '../types';
import { computeSiteRisk, computeActivityRisk, computeBarrierFailures, computePatterns } from '../utils/riskEngine';

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

function generateResponse(query: string, reports: ReturnType<typeof useApp>['reports']): { content: string; sourceIds: string[] } {
  if (reports.length === 0) {
    return {
      content: "No dataset is currently loaded. Please upload a safety dataset to ask questions about your safety data.",
      sourceIds: []
    };
  }

  const q = query.toLowerCase();
  const sifReports = reports.filter(r => r.sif_potential === 'YES');
  const criticalReports = reports.filter(r => r.severity === 'Critical' || r.risk_level === 'CRITICAL');
  const siteRisks = computeSiteRisk(reports);
  const activityRisks = computeActivityRisk(reports);
  const barriers = computeBarrierFailures(reports);
  const patterns = computePatterns(reports);

  // ─ Biggest risk ─
  if (q.includes('biggest') && (q.includes('risk') || q.includes('danger'))) {
    const topSite = siteRisks[0];
    const topActivity = activityRisks[0];
    const topBarrier = barriers[0];
    return {
      content: `Based on the current dataset of ${reports.length} reports:\n\n` +
        `**Highest-risk site:** ${topSite?.site || 'N/A'} (${topSite?.sif_count || 0} SIF potential reports, risk level: ${topSite?.risk_level || 'N/A'})\n\n` +
        `**Highest-risk activity:** ${topActivity?.activity || 'N/A'} (${topActivity?.sif_count || 0} SIF potential reports, avg risk score: ${topActivity?.avg_risk_score || 0})\n\n` +
        `**Most common barrier failure:** ${topBarrier?.barrier || 'N/A'} (found in ${topBarrier?.count || 0} reports, ${topBarrier?.percentage || 0}% of dataset)\n\n` +
        `**Overall:** ${sifReports.length} reports (${Math.round(sifReports.length / reports.length * 100)}%) show SIF potential, and ${criticalReports.length} are classified as critical.`,
      sourceIds: sifReports.slice(0, 5).map(r => r.id)
    };
  }

  // ─ Site risk ─
  if (q.includes('site') && (q.includes('most') || q.includes('highest') || q.includes('risk'))) {
    if (siteRisks.length === 0 || siteRisks[0].site === 'Unknown') {
      return { content: "Site data is not available in the current dataset. Please ensure your dataset has a site or location column.", sourceIds: [] };
    }
    const top = siteRisks.slice(0, 3);
    const content = `**Top Risk Sites:**\n\n` +
      top.map((s, i) => `${i + 1}. **${s.site}** — ${s.risk_level} risk · ${s.sif_count} SIF potential reports · ${s.total_reports} total reports · Top failure: ${s.top_barrier_failure}`).join('\n\n');
    return { content, sourceIds: sifReports.filter(r => r.site === top[0]?.site).slice(0, 5).map(r => r.id) };
  }

  // ─ Confined space ─
  if (q.includes('confined')) {
    const csReports = reports.filter(r =>
      (r.life_saving_rule || '').includes('Confined Space') ||
      (r.activity || '').includes('Confined Space') ||
      (r.report_text || '').toLowerCase().includes('confined space')
    );
    const sif = csReports.filter(r => r.sif_potential === 'YES');
    if (csReports.length === 0) {
      return { content: "No confined space reports found in the current dataset.", sourceIds: [] };
    }
    return {
      content: `**Confined Space Reports:**\n\nFound **${csReports.length}** confined space-related reports:\n- ${sif.length} with SIF potential\n- ${csReports.filter(r => r.severity === 'Critical').length} classified as critical\n\nCommon barriers failed: ${[...new Set(csReports.map(r => r.barrier_failure).filter(Boolean))].slice(0, 3).join(', ')}`,
      sourceIds: csReports.slice(0, 5).map(r => r.id)
    };
  }

  // ─ Barrier failure ─
  if (q.includes('barrier') || q.includes('control failure') || q.includes('common failed')) {
    if (barriers.length === 0) {
      return { content: "No barrier failure data available in the current dataset.", sourceIds: [] };
    }
    const content = `**Most Common Failed Safety Barriers:**\n\n` +
      barriers.slice(0, 5).map((b, i) => `${i + 1}. **${b.barrier}** — ${b.count} occurrences (${b.percentage}% of reports)`).join('\n\n');
    return { content, sourceIds: reports.filter(r => r.barrier_failure === barriers[0]?.barrier).slice(0, 5).map(r => r.id) };
  }

  // ─ Life-saving rule ─
  if (q.includes('rule') || q.includes('lsr') || q.includes('life-saving') || q.includes('life saving')) {
    const ruleCounts: Record<string, number> = {};
    for (const r of reports) {
      const rule = r.life_saving_rule || 'Unknown';
      ruleCounts[rule] = (ruleCounts[rule] || 0) + 1;
    }
    const sorted = Object.entries(ruleCounts).sort((a, b) => b[1] - a[1]);
    const content = `**Life-Saving Rule Frequency:**\n\n` +
      sorted.slice(0, 5).map(([rule, count], i) => `${i + 1}. **${rule}** — ${count} reports`).join('\n\n');
    return { content, sourceIds: [] };
  }

  // ─ Activity risk ─
  if (q.includes('activity') || q.includes('riskier') || q.includes('risky activity')) {
    if (activityRisks.length === 0) {
      return { content: "No activity data available in the current dataset.", sourceIds: [] };
    }
    const content = `**Highest-Risk Activities:**\n\n` +
      activityRisks.slice(0, 5).map((a, i) => `${i + 1}. **${a.activity}** — ${a.sif_count} SIF potential, avg risk score: ${a.avg_risk_score}, top failure: ${a.top_barrier_failure}`).join('\n\n');
    return { content, sourceIds: activityRisks[0] ? reports.filter(r => r.activity === activityRisks[0].activity).slice(0, 5).map(r => r.id) : [] };
  }

  // ─ Critical count ─
  if (q.includes('critical')) {
    return {
      content: `**Critical Reports Summary:**\n\nThe dataset contains **${criticalReports.length}** critical-severity reports out of ${reports.length} total (${Math.round(criticalReports.length / reports.length * 100)}%).\n\nSites affected: ${[...new Set(criticalReports.map(r => r.site).filter(Boolean))].slice(0, 5).join(', ') || 'N/A'}\n\nActivities: ${[...new Set(criticalReports.map(r => r.activity).filter(Boolean))].slice(0, 4).join(', ') || 'N/A'}`,
      sourceIds: criticalReports.slice(0, 5).map(r => r.id)
    };
  }

  // ─ Patterns ─
  if (q.includes('pattern') || q.includes('recurring')) {
    if (patterns.length === 0) {
      return { content: "No significant recurring patterns were detected in the current dataset.", sourceIds: [] };
    }
    const content = `**Top Recurring Safety Patterns:**\n\n` +
      patterns.slice(0, 4).map((p, i) => `${i + 1}. **${p.name}** — found in ${p.frequency} reports (${p.risk_level} risk)`).join('\n\n');
    return { content, sourceIds: patterns[0]?.report_ids.slice(0, 5) || [] };
  }

  // ─ SIF ─
  if (q.includes('sif') || q.includes('serious') || q.includes('fatality')) {
    return {
      content: `**SIF Potential Summary:**\n\n**${sifReports.length}** reports (${Math.round(sifReports.length / reports.length * 100)}%) show SIF potential in the current dataset.\n\nMost common activities in SIF reports: ${[...new Set(sifReports.map(r => r.activity).filter(Boolean))].slice(0, 4).join(', ')}\n\nMost common life-saving rules: ${[...new Set(sifReports.map(r => r.life_saving_rule).filter(Boolean))].slice(0, 3).join(', ')}`,
      sourceIds: sifReports.slice(0, 5).map(r => r.id)
    };
  }

  // ─ Default ─
  return {
    content: `I can help you analyze the safety dataset (${reports.length} reports loaded).\n\nTry asking:\n- "What is the biggest safety risk?"\n- "Which site has the most SIF potential?"\n- "Show confined space reports"\n- "What are the top barrier failures?"\n- "Which life-saving rule appears most?"\n- "Show critical reports"`,
    sourceIds: []
  };
}

export default function CopilotPage() {
  const { reports } = useApp();
  const [messages, setMessages] = useState<CopilotMessage[]>([
    {
      id: '0',
      role: 'assistant',
      content: `Hello! I'm **SafeSense Copilot**.\n\nI can answer questions about your uploaded safety dataset. Try asking about high-risk sites, barrier failures, SIF potential reports, recurring patterns, or specific activities.\n\n*Responses are based on the uploaded dataset only.*`,
      timestamp: new Date().toISOString(),
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: CopilotMessage = { id: Date.now().toString(), role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    await new Promise(r => setTimeout(r, 600));
    const { content, sourceIds } = generateResponse(text, reports);
    const assistantMsg: CopilotMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content,
      timestamp: new Date().toISOString(),
      source_reports: sourceIds,
    };
    setMessages(prev => [...prev, assistantMsg]);
    setLoading(false);
  }

  function renderContent(text: string) {
    return text.split('\n').map((line, i) => {
      const bold = line.replace(/\*\*(.+?)\*\*/g, '<strong class="font-bold text-slate-900">$1</strong>');
      return <p key={i} className="text-sm text-slate-700 leading-relaxed" dangerouslySetInnerHTML={{ __html: bold || '&nbsp;' }} />;
    });
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col space-y-4 animate-in">
      <div>
        <h1 className="section-title flex items-center gap-2"><MessageSquare className="w-6 h-6 text-blue-600" />Safety Copilot</h1>
        <p className="section-sub mb-2">Ask questions about your safety dataset. Responses are based on uploaded data only.</p>
      </div>

      <div className="flex-1 flex gap-5 min-h-0">
        {/* Chat area */}
        <div className="flex-1 flex flex-col bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  msg.role === 'assistant' ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-700'
                }`}>
                  {msg.role === 'assistant' ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
                </div>
                <div className={`max-w-[80%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1.5`}>
                  <div className={`rounded-xl px-4 py-3 shadow-xs ${
                    msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-slate-50 border border-slate-200'
                  }`}>
                    {msg.role === 'user' ? (
                      <p className="text-sm leading-relaxed">{msg.content}</p>
                    ) : (
                      <div className="space-y-1">{renderContent(msg.content)}</div>
                    )}
                  </div>
                  {msg.source_reports && msg.source_reports.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Database className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-xs text-slate-500 font-medium">Source reports:</span>
                      {msg.source_reports.map(id => (
                        <span key={id} className="text-xs bg-slate-100 text-slate-600 border border-slate-200 px-1.5 py-0.5 rounded font-mono font-medium">{id}</span>
                      ))}
                    </div>
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
                  <span className="text-sm text-slate-600 font-medium">Analyzing dataset...</span>
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
                placeholder="Ask about your safety data..."
              />
              <button onClick={() => sendMessage(input)} disabled={!input.trim() || loading} className="btn-primary px-4">
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Suggested questions sidebar */}
        <div className="w-64 flex-shrink-0 hidden md:block">
          <div className="card h-full flex flex-col justify-between p-5">
            <div>
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Suggested Questions</h3>
              <div className="space-y-2">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(q)}
                    className="w-full text-left text-xs font-medium text-slate-700 hover:text-blue-700 bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-200 p-2.5 rounded-lg transition-all"
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

import { useNavigate } from 'react-router-dom';
import {
  Shield, Brain, TrendingUp, AlertTriangle, GitBranch,
  CheckCircle, ArrowRight, Upload, Play, Zap, Target, Eye, BarChart2,
} from 'lucide-react';

const PIPELINE_STEPS = [
  { icon: '📋', label: 'Safety Reports',      sub: 'Unsafe Act · Near Miss · Incident' },
  { icon: '🤖', label: 'AI / NLP Engine',     sub: 'Text Processing · Entity Extraction' },
  { icon: '⚠️', label: 'Risk Detection',      sub: 'SIF Potential · Risk Score' },
  { icon: '📌', label: 'Safety Rule Mapping', sub: 'Life-Saving Rules · Barriers' },
  { icon: '🔁', label: 'Pattern Discovery',    sub: 'Recurring Precursors · Clusters' },
  { icon: '✅', label: 'Preventive Action',    sub: 'Recommendations · Review' },
];

const REPORT_TYPES = [
  { icon: '⚡', title: 'Unsafe Act',       color: 'border-orange-200 bg-orange-50/60', textColor: 'text-orange-700', desc: 'A person doing something unsafe — deviation from an established safety procedure or accepted safe practice.' },
  { icon: '🏗️', title: 'Unsafe Condition', color: 'border-amber-200 bg-amber-50/60',   textColor: 'text-amber-700',  desc: 'A physical condition or environment that increases the probability of an accident or incident occurring.' },
  { icon: '🔶', title: 'Near Miss',        color: 'border-yellow-200 bg-yellow-50/60', textColor: 'text-yellow-700', desc: 'An unplanned event that did not result in injury or damage but had the potential to do so — a warning signal.' },
  { icon: '🚨', title: 'Incident',         color: 'border-red-200 bg-red-50/60',       textColor: 'text-red-700',    desc: 'An unplanned event that caused or could have caused injury, illness, or damage. A critical learning opportunity.' },
];

const SIF_EXAMPLES = [
  'Confined-space entry without required atmospheric testing',
  'Maintenance performed without energy isolation (LOTO)',
  'Hot work carried out without a valid permit or fire watch',
  'Worker positioned in the line of fire of a suspended load',
  'Working at height without fall-arrest protection',
  'Exposure to live electrical conductors without isolation',
];

const FEATURES = [
  { icon: Brain,      title: 'AI-Powered NLP Analysis',   desc: 'Natural language processing reads, understands, and classifies safety observations automatically.' },
  { icon: Target,     title: 'SIF Precursor Detection',   desc: 'Identifies conditions that may indicate elevated potential for a serious injury or fatality.' },
  { icon: Eye,        title: 'Explainable AI',             desc: 'Shows exactly which phrases triggered the risk flag and why — no black-box decisions.' },
  { icon: GitBranch,  title: 'Pattern Discovery',        desc: 'Discovers recurring safety failure patterns across sites and activities using clustering.' },
  { icon: TrendingUp, title: 'Trend Intelligence',      desc: 'Detects rising frequencies of safety precursors over time to enable earlier intervention.' },
  { icon: BarChart2,  title: 'Executive Dashboard',     desc: 'KPI-driven dashboard for HSE leadership to prioritize action and track safety performance.' },
];

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="space-y-16 animate-in">

      {/* ─── Hero ─────────────────────────────────────────────────── */}
      <section className="text-center py-12">
        <div className="max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 text-blue-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-wider mb-6">
            <Shield className="w-4 h-4 text-blue-600" />
            Enterprise Safety Intelligence Platform
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-slate-900 leading-tight mb-5 tracking-tight">
            From Safety Reports to{' '}
            <span className="text-blue-600 block">Preventive Action</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-600 max-w-2xl mx-auto mb-10 leading-relaxed">
            AI-powered safety intelligence for identifying serious-risk precursors before they become serious incidents.
          </p>
          <div className="flex flex-col sm:flex-row gap-3.5 justify-center">
            <button onClick={() => navigate('/analysis')} className="btn-primary text-base px-7 py-3">
              <Brain className="w-5 h-5" />
              Analyze a Report
            </button>
            <button onClick={() => navigate('/upload')} className="btn-secondary text-base px-7 py-3 bg-white hover:bg-slate-50 border-slate-300">
              <Upload className="w-5 h-5" />
              Upload Dataset
            </button>
            <button onClick={() => navigate('/dashboard')} className="btn-secondary text-base px-7 py-3 bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100">
              <BarChart2 className="w-5 h-5" />
              View Dashboard
            </button>
          </div>
        </div>
      </section>

      {/* ─── Pipeline ────────────────────────────────────────────── */}
      <section className="border-t border-slate-200 pt-12">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-2">How SafeSense AI Works</h2>
          <p className="text-slate-500 text-center mb-10 text-sm">From raw safety report text to actionable intelligence — in seconds.</p>
          <div className="flex flex-wrap justify-center items-center gap-3">
            {PIPELINE_STEPS.map((step, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="pipeline-node flex flex-col items-center min-w-[140px] cursor-default bg-white border border-slate-200 shadow-xs p-4 rounded-xl">
                  <span className="text-2xl mb-1.5">{step.icon}</span>
                  <span className="font-bold text-slate-900 text-xs">{step.label}</span>
                  <span className="text-slate-500 text-xs mt-0.5">{step.sub}</span>
                </div>
                {i < PIPELINE_STEPS.length - 1 && (
                  <ArrowRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Why it matters ──────────────────────────────────────── */}
      <section className="border-t border-slate-200 pt-12">
        <div className="max-w-6xl mx-auto">
          <div className="grid md:grid-cols-2 gap-10 items-center">
            <div>
              <h2 className="text-3xl font-bold text-slate-900 mb-4 tracking-tight">Why Safety Intelligence Matters</h2>
              <p className="text-slate-600 leading-relaxed mb-4">
                Organizations receive large volumes of safety observations, unsafe-act reports, near-miss records, and incident reports every day. Critical high-risk information can be buried within large amounts of unstructured text.
              </p>
              <p className="text-slate-600 leading-relaxed mb-6">
                Manual review is slow, inconsistent, and can miss patterns that only become visible across hundreds of reports. SafeSense AI helps safety teams:
              </p>
              <ul className="space-y-2.5">
                {[
                  'Find high-risk reports faster with AI classification',
                  'Understand why a report is risky with explainable evidence',
                  'Identify repeated precursor patterns across sites',
                  'Detect failed safety controls before they lead to incidents',
                  'Prioritize corrective actions with confidence',
                ].map((item, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700">
                    <CheckCircle className="w-4 h-4 text-green-600 mt-0.5 flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {REPORT_TYPES.map(rt => (
                <div key={rt.title} className={`card border ${rt.color} hover:shadow-md transition-all cursor-default p-5`}>
                  <div className="text-2xl mb-2">{rt.icon}</div>
                  <div className={`font-bold text-sm mb-1 ${rt.textColor}`}>{rt.title}</div>
                  <p className="text-slate-600 text-xs leading-relaxed">{rt.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─── What is SIF ─────────────────────────────────────────── */}
      <section className="border-t border-slate-200 pt-12">
        <div className="max-w-4xl mx-auto">
          <div className="card border-red-200 bg-red-50/40 p-6 md:p-8">
            <div className="flex items-start gap-5">
              <div className="w-12 h-12 rounded-xl bg-red-100 border border-red-200 flex items-center justify-center flex-shrink-0 text-red-600">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h2 className="text-xl font-bold text-slate-900">What is SIF?</h2>
                  <span className="badge-sif">SIF = Serious Injury or Fatality</span>
                </div>
                <p className="text-slate-700 mb-5 leading-relaxed">
                  A <strong className="text-red-700">SIF precursor</strong> is a warning sign or unsafe condition that may indicate the potential for a serious injury or fatality. SafeSense AI identifies these precursors in safety reports — <em>not</em> to predict that a fatality will definitely occur, but to help safety teams recognize elevated-risk conditions earlier and act preventively.
                </p>
                <div>
                  <p className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-3">Examples of SIF precursors:</p>
                  <div className="grid sm:grid-cols-2 gap-2.5">
                    {SIF_EXAMPLES.map((ex, i) => (
                      <div key={i} className="flex items-start gap-2.5 text-xs text-slate-700 bg-white border border-red-100 rounded-lg p-3 shadow-xs">
                        <AlertTriangle className="w-3.5 h-3.5 text-red-600 mt-0.5 flex-shrink-0" />
                        {ex}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Features ─────────────────────────────────────────────── */}
      <section className="border-t border-slate-200 pt-12">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-2">Platform Capabilities</h2>
          <p className="text-slate-500 text-center text-sm mb-10">Everything an HSE team needs in one intelligent platform.</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="card-hover">
                <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-200 flex items-center justify-center mb-3.5 text-blue-600">
                  <Icon className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-slate-900 mb-1.5 text-base">{title}</h3>
                <p className="text-slate-600 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA ──────────────────────────────────────────────────── */}
      <section className="border-t border-slate-200 pt-12">
        <div className="max-w-3xl mx-auto text-center">
          <div className="card border-blue-200 bg-blue-50/50 p-8 md:p-10">
            <Zap className="w-10 h-10 text-blue-600 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Get Started</h2>
            <p className="text-slate-600 mb-6 text-sm leading-relaxed max-w-xl mx-auto">
              Upload your CSV of safety reports and see the full platform in action — AI analysis, risk scoring, pattern discovery, early warnings, and corrective actions. All data is processed and stored in the backend database.
            </p>
            <div className="flex flex-col sm:flex-row gap-3.5 justify-center">
              <button onClick={() => navigate('/upload')} className="btn-primary text-base px-8 py-3">
                <Upload className="w-5 h-5" />
                Upload Reports
              </button>
              <button onClick={() => navigate('/analysis')} className="btn-secondary text-base px-8 py-3 bg-white hover:bg-slate-50 border-slate-300">
                <Play className="w-5 h-5" />
                Try Single Analysis
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 pt-8 pb-4 text-center">
        <div className="flex items-center justify-center gap-2 mb-2">
          <Shield className="w-4 h-4 text-blue-600" />
          <span className="font-bold text-slate-900">SafeSense AI</span>
        </div>
        <p className="text-slate-500 text-xs">Enterprise Safety Intelligence Platform · AI supports HSE decision-making. Final decisions remain with authorized safety personnel.</p>
      </footer>

    </div>
  );
}

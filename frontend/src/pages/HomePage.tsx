import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion, useInView, useReducedMotion } from 'framer-motion';
import {
  Shield, ShieldCheck, Brain, TrendingUp, AlertTriangle, GitBranch, CheckCircle,
  ArrowRight, ArrowDown, Upload, Zap, Target, Eye, BarChart2, FileText, ScanSearch,
  Activity, Layers, MessageSquare, Lock, UserCheck, Play,
  AlertOctagon, Radio, Gauge, AlertCircle, LogIn,
} from 'lucide-react';
import { useApp } from '../context/AppContext';

/* ══════════════════════════════════════════════════════════════════════════════
   Showcase data — clearly labeled illustrative/demo values (NOT live backend
   results). The pipeline animation is a visual explanation of the workflow.
   ══════════════════════════════════════════════════════════════════════════════ */

const SHOWCASE_REPORTS = [
  { id: 'SAF-2024-0142', fragments: ['Confined space entry…', 'Gas testing not completed…', 'Energy isolation not applied…'] },
  { id: 'SAF-2024-0177', fragments: ['Scaffold erection at height…', 'Fall-arrest harness unclipped…', 'Rescue plan not in place…'] },
  { id: 'SAF-2024-0203', fragments: ['Pump maintenance underway…', 'LOTO not verified…', 'Live electrical panel open…'] },
  { id: 'SAF-2024-0236', fragments: ['Hot work permit issued…', 'Fire watch absent…', 'Combustibles within 10 m…'] },
];

const HERO_INDICATORS = [
  { label: 'SIF POTENTIAL', value: 33, tone: 'text-red-400', icon: Target },
  { label: 'CRITICAL', value: 12, tone: 'text-orange-400', icon: AlertCircle },
  { label: 'ACTIVE PATTERNS', value: 5, tone: 'text-blue-400', icon: GitBranch },
  { label: 'RISING PRECURSORS', value: 3, tone: 'text-amber-400', icon: TrendingUp },
];

const WORKFLOW_STAGES = [
  { n: '01', key: 'INGEST',   icon: FileText,    title: 'Ingest',    desc: 'Safety reports arrive as free text — observations, near misses, incidents — via upload or direct entry.' },
  { n: '02', key: 'UNDERSTAND', icon: Brain,    title: 'Understand', desc: 'NLP extracts hazards, activities and safety concepts, with multilingual detection and PII redaction.' },
  { n: '03', key: 'DETECT',   icon: Target,      title: 'Detect',    desc: 'Deterministic engines flag SIF precursors and map Life-Saving Rule exposure with full evidence.' },
  { n: '04', key: 'EXPLAIN',  icon: ScanSearch,  title: 'Explain',   desc: 'Every risk score is explainable — weighted factors, failed barriers and the exact phrases that triggered them.' },
  { n: '05', key: 'DISCOVER', icon: GitBranch,   title: 'Discover',  desc: 'Pattern clustering and trend analysis surface recurring precursor combinations across sites and time.' },
  { n: '06', key: 'ACT',      icon: CheckCircle, title: 'Act',       desc: 'Preventive actions, HITL review and grounded Copilot answers turn intelligence into intervention.' },
];

const WHY_STEPS = [
  {
    label: 'THE PROBLEM', tone: 'slate',
    icon: Layers,
    title: 'Safety teams drown in unstructured observations.',
    desc: 'Thousands of free-text reports, near misses and unsafe-condition notes arrive every month across sites, units and activities.',
  },
  {
    label: 'THE GAP', tone: 'amber',
    icon: AlertCircle,
    title: 'Critical precursor signals stay buried.',
    desc: 'The report that says “gas testing not completed” rarely announces itself. Serious-risk signals hide across reports, sites, activities and time.',
  },
  {
    label: 'THE SOLUTION', tone: 'blue',
    icon: ShieldCheck,
    title: 'SafeSense connects report-level evidence to system-level intelligence.',
    desc: 'Deterministic engines score every report, map barriers and Life-Saving Rules, and cluster recurring exposures into patterns you can act on.',
  },
];

const SIF_CHAIN = [
  { label: 'SIF PRECURSOR', detail: 'Elevated-risk condition observed in a report', icon: AlertTriangle },
  { label: 'FAILED BARRIER', detail: 'The control that should have prevented exposure', icon: Shield },
  { label: 'EXPOSURE', detail: 'A person was (or could have been) in the line of fire', icon: Activity },
  { label: 'POTENTIAL SERIOUS CONSEQUENCE', detail: 'What could have happened — and what prevention avoids', icon: AlertCircle },
];

const CAPABILITIES = [
  { icon: Target,      title: 'SIF Precursor Detection',      desc: 'Deterministic identification of conditions with elevated serious-injury potential — evidence-first, explainable.' },
  { icon: ScanSearch,  title: 'Explainable Risk Analysis',    desc: 'Weighted factor breakdowns and evidence phrases for every score. No black boxes — every point is accounted for.' },
  { icon: Shield,      title: 'Life-Saving Rule Mapping',     desc: 'Automatic LSR classification across the rule set, with secondary-rule context and confidence reasoning.' },
  { icon: Layers,      title: 'Barrier Failure Intelligence', desc: 'Which controls failed, how often, and in combination with which activities and hazards.' },
  { icon: GitBranch,   title: 'Pattern Discovery',            desc: 'Similarity clustering exposes recurring precursor combinations that no single report reveals.' },
  { icon: TrendingUp,  title: 'Trend & Anomaly Detection',    desc: 'Rising precursor frequencies and site concentration spikes surfaced with early warnings.' },
  { icon: MessageSquare, title: 'Grounded Safety Copilot',    desc: 'Ask questions in plain language; get answers synthesized strictly from your verified safety database, with citations.' },
  { icon: Lock,        title: 'PII Protection',               desc: 'Personal identifiers are detected and redacted before analysis, storage and synthesis.' },
  { icon: UserCheck,   title: 'Human-in-the-Loop Review',     desc: 'Confirm, correct or reject AI analysis. Reviews are audit-trailed; humans stay the authority.' },
];

/* ══════════════════════════════════════════════════════════════════════════════
   Animation helpers
   ══════════════════════════════════════════════════════════════════════════════ */

function useCountUp(target: number, active: boolean, duration = 1100): number {
  const [value, setValue] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!active) return;
    if (reduced) { setValue(target); return; }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, target, duration, reduced]);
  return value;
}

/* ─── Hero: animated intelligence pipeline console ──────────────────────────── */

interface StageNode {
  id: string;
  label: string;
  sub: string;
  icon: typeof Brain;
  alert?: boolean;
  done?: boolean;
}

const STAGE_SEQUENCE: StageNode[] = [
  { id: 'nlp',      label: 'AI / NLP',            sub: 'Concepts extracted', icon: Brain },
  { id: 'sif',      label: 'SIF PRECURSOR DETECTED', sub: 'Elevated serious-risk signal', icon: Target, alert: true },
  { id: 'risk',     label: 'RISK SCORE: 89',      sub: 'CRITICAL', icon: Gauge, alert: true },
  { id: 'barrier',  label: 'BARRIER FAILURE',     sub: 'Gas Testing Not Completed', icon: Shield, alert: true },
  { id: 'pattern',  label: 'PATTERN MATCH',       sub: 'Recurring Confined-Space Exposure', icon: GitBranch },
  { id: 'action',   label: 'PREVENTIVE ACTION',   sub: 'Verify gas testing & isolation before entry', icon: CheckCircle, done: true },
];

function PipelineConsole() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: false, margin: '-40px' });
  const reduced = useReducedMotion();

  const [reportIdx, setReportIdx] = useState(0);
  const [step, setStep] = useState(0);          // 0..STAGE_SEQUENCE.length (length = complete)
  const [cycle, setCycle] = useState(0);        // forces re-type of the report fragment

  const report = SHOWCASE_REPORTS[reportIdx % SHOWCASE_REPORTS.length];

  useEffect(() => {
    if (!inView || reduced) {
      if (reduced) setStep(STAGE_SEQUENCE.length);
      return;
    }
    const isLast = step >= STAGE_SEQUENCE.length;
    const delay = isLast ? 2600 : 1150;
    const t = setTimeout(() => {
      if (isLast) {
        setStep(0);
        setCycle(c => c + 1);
        setReportIdx(i => (i + 1) % SHOWCASE_REPORTS.length);
      } else {
        setStep(s => s + 1);
      }
    }, delay);
    return () => clearTimeout(t);
  }, [step, inView, reduced]);

  const stagesShown = reduced ? STAGE_SEQUENCE.length : step;

  return (
    <div ref={ref} className="relative">
      {/* console frame */}
      <div className="relative rounded-2xl border border-slate-700/60 bg-slate-900/80 backdrop-blur shadow-2xl shadow-black/40 overflow-hidden">
        {/* header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60 bg-slate-900">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 motion-reduce:animate-none" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
            <span className="text-[11px] font-bold tracking-[0.14em] text-slate-300 uppercase">Intelligence Workflow</span>
          </div>
          <span className="text-[10px] font-semibold tracking-wider text-amber-400/90 bg-amber-400/10 border border-amber-400/20 px-2 py-0.5 rounded-full uppercase">
            Illustrative · Demo data
          </span>
        </div>

        <div className="p-4 sm:p-5">
          {/* report card */}
          <div className="rounded-xl border border-slate-700/60 bg-slate-800/70 p-3.5 sm:p-4">
            <div className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2 text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                <FileText className="w-3.5 h-3.5" aria-hidden />
                Safety Report · {report.id}
              </div>
              <span className="text-[10px] font-mono text-slate-500">raw text</span>
            </div>
            <div className="space-y-1.5" aria-live="off">
              {report.fragments.map((frag, i) => (
                <motion.div
                  key={`${report.id}-${cycle}-${i}`}
                  initial={reduced ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: reduced ? 0 : i * 0.35, duration: 0.4 }}
                  className="flex items-center gap-2"
                >
                  <span className="w-1 h-1 rounded-full bg-blue-400 flex-shrink-0" aria-hidden />
                  <span className="text-[13px] text-slate-200 font-medium">{frag}</span>
                </motion.div>
              ))}
            </div>
          </div>

          {/* connector rail with pulses */}
          <div className="relative h-6" aria-hidden>
            <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none" viewBox="0 0 10 24">
              <line x1="5" y1="0" x2="5" y2="24" stroke="rgb(51 65 85)" strokeWidth="2" />
              <line x1="5" y1="0" x2="5" y2="24" stroke="rgb(59 130 246)" strokeWidth="2"
                strokeDasharray="4 6" className="safesense-flow-line" opacity={reduced ? 0.4 : 0.9} />
            </svg>
          </div>

          {/* stage nodes */}
          <ol className="space-y-2" aria-label="Intelligence pipeline stages (illustrative)">
            {STAGE_SEQUENCE.map((s, i) => {
              const active = stagesShown === i + 1;
              const completed = stagesShown > i + 1 || stagesShown === STAGE_SEQUENCE.length && active;
              const visible = stagesShown >= i + 1 || reduced;
              const Icon = s.icon;
              return (
                <motion.li
                  key={s.id}
                  initial={reduced ? false : { opacity: 0, y: 10 }}
                  animate={visible ? { opacity: 1, y: 0 } : { opacity: 0.25, y: 0 }}
                  transition={{ duration: 0.35 }}
                  className={`relative rounded-xl border px-3.5 py-3 flex items-center gap-3 transition-colors duration-300 ${
                    active
                      ? 'border-blue-500/70 bg-blue-500/10 shadow-lg shadow-blue-950/60'
                      : s.alert && (active || completed)
                        ? 'border-red-500/40 bg-red-500/[0.07]'
                        : s.done && completed
                          ? 'border-emerald-500/40 bg-emerald-500/[0.07]'
                          : 'border-slate-700/50 bg-slate-800/40'
                  }`}
                  aria-hidden={!visible}
                >
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                    active ? 'bg-blue-500/20 border-blue-400/50 text-blue-300 safesense-node-glow'
                    : s.alert && completed ? 'bg-red-500/15 border-red-500/40 text-red-300'
                    : s.done && completed ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                    : 'bg-slate-700/40 border-slate-600/50 text-slate-400'
                  }`}>
                    <Icon className="w-4 h-4" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className={`text-[12.5px] font-bold tracking-wide ${s.alert && completed ? 'text-red-300' : s.done && completed ? 'text-emerald-300' : active ? 'text-blue-200' : 'text-slate-300'}`}>
                      {s.label}
                    </div>
                    <div className="text-[11.5px] text-slate-400 truncate">{s.sub}</div>
                  </div>
                  {active && (
                    <span className="flex-shrink-0 w-4 h-4 border-2 border-blue-400/40 border-t-blue-300 rounded-full animate-spin motion-reduce:animate-none" aria-hidden />
                  )}
                  {completed && !active && (
                    <CheckCircle className={`w-4 h-4 flex-shrink-0 ${s.done ? 'text-emerald-400' : 'text-slate-500'}`} aria-hidden />
                  )}
                  {active && (
                    <span className="absolute right-3 -top-2 text-[9px] font-bold tracking-widest text-blue-300 bg-slate-900 border border-blue-500/40 rounded-full px-1.5 py-0.5 uppercase">
                      Processing
                    </span>
                  )}
                </motion.li>
              );
            })}
          </ol>
        </div>

        {/* footer strip */}
        <div className="px-4 py-2.5 border-t border-slate-700/60 bg-slate-900/90 flex items-center justify-between">
          <span className="text-[10px] text-slate-500 font-medium">Deterministic engines · Evidence-grounded · Human-authorized</span>
          <Radio className="w-3.5 h-3.5 text-slate-600" aria-hidden />
        </div>
      </div>
    </div>
  );
}

/* ─── Hero indicators (illustrative counts) ─────────────────────────────────── */

function IndicatorTiles() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: '-20px' });
  const values = HERO_INDICATORS.map(h => useCountUp(h.value, inView));

  return (
    <div ref={ref} className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {HERO_INDICATORS.map(({ label, tone, icon: Icon }, i) => (
        <div key={label} className="rounded-xl border border-slate-700/60 bg-slate-900/70 backdrop-blur px-3.5 py-3">
          <div className="flex items-center gap-1.5 text-[10px] font-bold tracking-wider text-slate-400 uppercase mb-1.5">
            <Icon className={`w-3.5 h-3.5 ${tone}`} aria-hidden />
            {label}
          </div>
          <div className={`text-2xl font-extrabold tabular-nums ${tone}`}>{values[i]}</div>
        </div>
      ))}
      <div className="col-span-2 sm:col-span-4 flex items-center gap-2 text-[10.5px] text-slate-500 font-medium">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400/80 flex-shrink-0" aria-hidden />
        Illustrative intelligence · demo dataset — connect your own data to see live values.
      </div>
    </div>
  );
}

/* ─── Main page ─────────────────────────────────────────────────────────────── */

const fadeUp = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '-60px' },
} as const;

export default function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const reduced = useReducedMotion();
  const { isAuthenticated } = useApp();

  const appPath = (path: string) => (isAuthenticated ? path : '/login');

  // "Watch the workflow" → smooth-scroll to the workflow section
  useEffect(() => {
    if (location.hash === '#workflow') {
      document.getElementById('workflow')?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' });
    }
  }, [location.hash, reduced]);

  return (
    <div className="bg-white min-h-screen">
      {/* ═══════════ PUBLIC HEADER ═══════════ */}
      <header className="sticky top-0 z-40 bg-slate-950/95 backdrop-blur border-b border-slate-800/80">
        <div className="max-w-7xl mx-auto px-6 md:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-md shadow-blue-950/50">
              <Shield className="w-5 h-5 text-white" aria-hidden />
            </div>
            <div className="leading-tight">
              <div className="font-bold text-white text-sm">SafeSense AI</div>
              <div className="text-[10px] font-semibold text-blue-400 uppercase tracking-wider">Safety Intelligence</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <button
                onClick={() => navigate('/app/dashboard')}
                className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              >
                Open Platform
              </button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="text-sm font-semibold text-slate-300 hover:text-white px-3 py-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                >
                  Sign in
                </button>
                <button
                  onClick={() => navigate('/login?mode=signup')}
                  className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  <LogIn className="w-4 h-4" aria-hidden />
                  Create account
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="space-y-20 md:space-y-24">

      {/* ═══════════ HERO ═══════════ */}
      <section className="relative px-6 md:px-8 pt-10 pb-14 md:pt-20 md:pb-24 overflow-hidden
                          bg-slate-950 text-white
                          bg-[radial-gradient(ellipse_at_top_left,rgba(37,99,235,0.18),transparent_55%),radial-gradient(ellipse_at_bottom_right,rgba(16,185,129,0.10),transparent_50%)]">
        {/* fine industrial grid */}
        <svg aria-hidden className="absolute inset-0 w-full h-full opacity-[0.045] pointer-events-none">
          <defs>
            <pattern id="hero-grid" width="48" height="48" patternUnits="userSpaceOnUse">
              <path d="M 48 0 L 0 0 0 48" fill="none" stroke="white" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#hero-grid)" />
        </svg>

        <div className="relative max-w-7xl mx-auto grid lg:grid-cols-2 gap-10 lg:gap-14 items-center">
          {/* Copy */}
          <div>
            <motion.div {...(reduced ? {} : fadeUp)} className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-400/30 text-blue-300 px-3.5 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-[0.14em] mb-6">
              <Shield className="w-3.5 h-3.5" aria-hidden />
              Enterprise Safety Intelligence Platform
            </motion.div>

            <motion.h1
              {...(reduced ? {} : { ...fadeUp, transition: { delay: 0.05, duration: 0.5 } })}
              className="text-4xl sm:text-5xl xl:text-6xl font-extrabold leading-[1.05] tracking-tight mb-5"
            >
              Safety Intelligence
              <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-sky-300 to-emerald-300">
                for the risks that matter most.
              </span>
            </motion.h1>

            <motion.p
              {...(reduced ? {} : { ...fadeUp, transition: { delay: 0.1, duration: 0.5 } })}
              className="text-lg text-slate-300 max-w-xl mb-4 leading-relaxed"
            >
              Turn thousands of unstructured safety observations into explainable SIF intelligence,
              recurring patterns, and preventive action.
            </motion.p>

            <motion.p
              {...(reduced ? {} : { ...fadeUp, transition: { delay: 0.14, duration: 0.5 } })}
              className="flex items-center gap-2 text-sm text-slate-400 font-medium mb-8"
            >
              <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" aria-hidden />
              AI-assisted. Evidence-grounded. Human-authorized.
            </motion.p>

            <motion.div
              {...(reduced ? {} : { ...fadeUp, transition: { delay: 0.18, duration: 0.5 } })}
              className="flex flex-col sm:flex-row gap-3"
            >
              <button onClick={() => navigate(appPath('/analysis'))} className="inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold px-6 py-3 rounded-xl shadow-lg shadow-blue-950/50 transition-all duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950">
                <Brain className="w-5 h-5" aria-hidden />
                Analyze a Report
              </button>
              <button onClick={() => navigate(appPath('/command-center'))} className="inline-flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-slate-600 text-slate-100 font-semibold px-6 py-3 rounded-xl transition-all duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950">
                <BarChart2 className="w-5 h-5" aria-hidden />
                Explore Intelligence
              </button>
              <a
                href="#workflow"
                onClick={e => { e.preventDefault(); document.getElementById('workflow')?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' }); }}
                className="inline-flex items-center justify-center gap-2 text-slate-300 hover:text-white font-semibold px-4 py-3 rounded-xl transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded-xl"
              >
                <Play className="w-4 h-4" aria-hidden />
                Watch the Workflow
              </a>
            </motion.div>

            {/* indicators */}
            <motion.div {...(reduced ? {} : { ...fadeUp, transition: { delay: 0.24, duration: 0.5 } })} className="mt-10">
              <IndicatorTiles />
            </motion.div>
          </div>

          {/* Animated pipeline console */}
          <motion.div
            initial={reduced ? false : { opacity: 0, y: 32, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.15, duration: 0.6 }}
          >
            <PipelineConsole />
          </motion.div>
        </div>
      </section>

      {/* ═══════════ WORKFLOW ═══════════ */}
      <section id="workflow" className="max-w-7xl mx-auto scroll-mt-20">
        <motion.div {...(reduced ? {} : fadeUp)} className="text-center mb-12">
          <p className="text-xs font-bold tracking-[0.18em] text-blue-600 uppercase mb-2">How it works</p>
          <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 tracking-tight mb-3">From raw reports to preventive action</h2>
          <p className="text-slate-500 max-w-2xl mx-auto">Six deterministic stages turn unstructured text into a connected safety intelligence system.</p>
        </motion.div>

        <ol className="relative grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {WORKFLOW_STAGES.map((stage, i) => {
            const Icon = stage.icon;
            return (
              <motion.li
                key={stage.n}
                initial={reduced ? false : { opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ delay: reduced ? 0 : i * 0.06, duration: 0.45 }}
                className="group relative card-hover p-6 cursor-default"
                tabIndex={0}
                aria-label={`Stage ${stage.n}: ${stage.title}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-blue-500 text-white flex items-center justify-center shadow-md shadow-blue-600/20 group-hover:scale-105 transition-transform duration-200">
                    <Icon className="w-5 h-5" aria-hidden />
                  </div>
                  <span className="text-4xl font-extrabold text-slate-100 select-none group-hover:text-blue-100 transition-colors" aria-hidden>{stage.n}</span>
                </div>
                <div className="text-[11px] font-bold tracking-[0.16em] text-blue-600 uppercase mb-1">{stage.key}</div>
                <h3 className="text-lg font-bold text-slate-900 mb-2">{stage.title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed">{stage.desc}</p>
                <div className="mt-4 h-0.5 w-10 bg-blue-600/80 rounded-full group-hover:w-16 transition-all duration-300" aria-hidden />
              </motion.li>
            );
          })}
        </ol>
      </section>

      {/* ═══════════ WHY SAFESENSE ═══════════ */}
      <section className="max-w-7xl mx-auto">
        <motion.div {...(reduced ? {} : fadeUp)} className="text-center mb-12">
          <p className="text-xs font-bold tracking-[0.18em] text-blue-600 uppercase mb-2">Why SafeSense</p>
          <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 tracking-tight">See the signal. Act before it becomes an incident.</h2>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-5">
          {WHY_STEPS.map((step, i) => {
            const Icon = step.icon;
            const toneRing = step.tone === 'amber' ? 'border-amber-200 bg-amber-50 text-amber-700'
              : step.tone === 'blue' ? 'border-blue-200 bg-blue-50 text-blue-700'
              : 'border-slate-200 bg-slate-100 text-slate-700';
            return (
              <motion.div
                key={step.label}
                initial={reduced ? false : { opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ delay: reduced ? 0 : i * 0.08, duration: 0.45 }}
                className="relative card p-7"
              >
                <div className={`inline-flex items-center gap-1.5 border rounded-full px-2.5 py-1 text-[10.5px] font-bold tracking-widest uppercase mb-5 ${toneRing}`}>
                  <Icon className="w-3.5 h-3.5" aria-hidden />
                  {step.label}
                </div>
                <h3 className="text-xl font-bold text-slate-900 mb-2.5 leading-snug">{step.title}</h3>
                <p className="text-slate-600 text-sm leading-relaxed">{step.desc}</p>
                {i < WHY_STEPS.length - 1 && (
                  <ArrowRight className="hidden md:block absolute top-1/2 -right-[22px] w-6 h-6 text-slate-300 z-10" aria-hidden />
                )}
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* ═══════════ SIF SECTION ═══════════ */}
      <section className="max-w-7xl mx-auto">
        <div className="rounded-3xl border border-red-100 bg-gradient-to-br from-red-50/80 via-white to-white p-8 md:p-12 shadow-sm">
          <motion.div {...(reduced ? {} : fadeUp)} className="max-w-3xl mb-10">
            <div className="flex items-center gap-3 mb-3">
              <AlertTriangle className="w-6 h-6 text-red-600" aria-hidden />
              <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 tracking-tight">SIF intelligence, explained honestly</h2>
            </div>
            <p className="text-slate-600 leading-relaxed">
              A <strong>Serious Injury or Fatality (SIF) precursor</strong> is a warning sign that a high-energy
              exposure was one failed barrier away from tragedy. SafeSense surfaces these precursors early
              so controls can be restored before exposure occurs.
            </p>
          </motion.div>

          {/* chain */}
          <ol className="grid gap-3 lg:grid-cols-4 lg:gap-0 lg:items-stretch mb-8">
            {SIF_CHAIN.map((node, i) => {
              const Icon = node.icon;
              return (
                <motion.li
                  key={node.label}
                  initial={reduced ? false : { opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-40px' }}
                  transition={{ delay: reduced ? 0 : i * 0.1, duration: 0.4 }}
                  className="relative"
                >
                  <div className="h-full bg-white border border-red-100 rounded-2xl p-5 lg:rounded-none lg:first:rounded-l-2xl lg:last:rounded-r-2xl shadow-xs">
                    <div className="flex items-center gap-2 mb-2.5">
                      <div className="w-8 h-8 rounded-lg bg-red-100 text-red-600 flex items-center justify-center flex-shrink-0">
                        <Icon className="w-4 h-4" aria-hidden />
                      </div>
                      <span className="text-[11px] font-extrabold tracking-wider text-red-700 uppercase">{node.label}</span>
                    </div>
                    <p className="text-[13px] text-slate-600 leading-relaxed">{node.detail}</p>
                  </div>
                  {i < SIF_CHAIN.length - 1 && (
                    <ArrowDown className="hidden lg:block absolute top-1/2 -right-[13px] -translate-y-1/2 w-6 h-6 text-red-300 z-10 bg-white rounded-full" aria-hidden />
                  )}
                </motion.li>
              );
            })}
          </ol>

          <motion.div {...(reduced ? {} : fadeUp)} className="flex items-start gap-3 bg-slate-900 text-slate-200 rounded-2xl p-5">
            <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" aria-hidden />
            <p className="text-sm leading-relaxed">
              <strong className="text-white">Safety boundary:</strong> SafeSense identifies elevated-risk precursors.
              It does not predict that a fatality will occur. Final safety decisions remain with authorized HSE personnel.
            </p>
          </motion.div>
        </div>
      </section>

      {/* ═══════════ CAPABILITIES ═══════════ */}
      <section className="max-w-7xl mx-auto">
        <motion.div {...(reduced ? {} : fadeUp)} className="text-center mb-12">
          <p className="text-xs font-bold tracking-[0.18em] text-blue-600 uppercase mb-2">Capabilities</p>
          <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 tracking-tight mb-3">One platform. The full prevention loop.</h2>
          <p className="text-slate-500 max-w-2xl mx-auto">Deterministic safety engines first, advisory AI second, humans always in command.</p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {CAPABILITIES.map((cap, i) => {
            const Icon = cap.icon;
            return (
              <motion.div
                key={cap.title}
                initial={reduced ? false : { opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ delay: reduced ? 0 : (i % 3) * 0.06, duration: 0.4 }}
                className="group card-hover p-6"
              >
                <div className="w-10 h-10 rounded-xl bg-slate-900 text-white flex items-center justify-center mb-4 group-hover:bg-blue-600 transition-colors duration-200">
                  <Icon className="w-5 h-5" aria-hidden />
                </div>
                <h3 className="font-bold text-slate-900 mb-1.5">{cap.title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed">{cap.desc}</p>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* ═══════════ FINAL CTA ═══════════ */}
      <section className="max-w-7xl mx-auto">
        <motion.div
          {...(reduced ? {} : fadeUp)}
          className="relative overflow-hidden rounded-3xl bg-slate-950 text-white px-8 py-14 md:px-16 md:py-16 text-center
                     bg-[radial-gradient(ellipse_at_top,rgba(37,99,235,0.25),transparent_60%)]"
        >
          <svg aria-hidden className="absolute inset-0 w-full h-full opacity-[0.05] pointer-events-none">
            <rect width="100%" height="100%" fill="url(#hero-grid)" />
          </svg>
          <div className="relative">
            <Zap className="w-9 h-9 text-blue-400 mx-auto mb-5" aria-hidden />
            <h2 className="text-3xl md:text-5xl font-extrabold tracking-tight mb-4">
              Turn observations into prevention.
            </h2>
            <p className="text-slate-300 max-w-xl mx-auto mb-9 leading-relaxed">
              Upload a dataset or analyze a single report — and watch SafeSense turn free text into
              explainable, actionable safety intelligence.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button onClick={() => navigate(appPath('/upload'))} className="inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 font-semibold px-7 py-3.5 rounded-xl shadow-lg shadow-blue-950/60 transition-all active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950">
                <Upload className="w-5 h-5" aria-hidden />
                Analyze a Report
              </button>
              <button onClick={() => navigate(appPath('/copilot'))} className="inline-flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-slate-600 font-semibold px-7 py-3.5 rounded-xl transition-all active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950">
                <MessageSquare className="w-5 h-5" aria-hidden />
                Open Safety Copilot
              </button>
              <button onClick={() => navigate(appPath('/dashboard'))} className="inline-flex items-center justify-center gap-2 bg-white/5 hover:bg-white/10 border border-slate-600 font-semibold px-7 py-3.5 rounded-xl transition-all active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950">
                <BarChart2 className="w-5 h-5" aria-hidden />
                Explore Dashboard
              </button>
            </div>
            <p className="mt-8 text-xs text-slate-500 font-medium flex items-center justify-center gap-2">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden />
              Final safety decisions remain with authorized HSE personnel.
            </p>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 pt-8 pb-4">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-blue-600" aria-hidden />
            <span className="font-bold text-slate-900 text-sm">SafeSense AI</span>
            <span className="text-slate-400 text-xs">· Enterprise Safety Intelligence Platform</span>
          </div>
          <p className="text-slate-500 text-xs text-center sm:text-right">
            AI supports HSE decision-making · Deterministic engines are authoritative · Humans authorize every action
          </p>
        </div>
      </footer>
      </div>
    </div>
  );
}

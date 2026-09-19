import { DetectedLanguage, LANGUAGE_DISPLAY, LANGUAGE_FLAG, MultilingualStats } from '../types';
import { Languages, AlertCircle, ArrowRightLeft } from 'lucide-react';

// ─── Language Badge ───────────────────────────────────────────────────────────
interface LanguageBadgeProps {
  language: DetectedLanguage;
  size?: 'sm' | 'md';
  showFlag?: boolean;
}

export function LanguageBadge({ language, size = 'md', showFlag = true }: LanguageBadgeProps) {
  const sizeClass = size === 'sm'
    ? 'px-2 py-0.5 text-xs'
    : 'px-2.5 py-0.5 text-xs';

  const colorClass: Record<DetectedLanguage, string> = {
    en: 'bg-blue-50 text-blue-700 border border-blue-200',
    kn: 'bg-orange-50 text-orange-700 border border-orange-200',
    hi: 'bg-green-50 text-green-700 border border-green-200',
    unknown: 'bg-slate-100 text-slate-600 border border-slate-200',
  };

  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-medium ${sizeClass} ${colorClass[language]}`}>
      {showFlag && <span className="text-xs">{LANGUAGE_FLAG[language]}</span>}
      {LANGUAGE_DISPLAY[language]}
    </span>
  );
}

// ─── Translation Badge ────────────────────────────────────────────────────────
interface TranslationBadgeProps {
  isTranslated: boolean;
  translationError?: string | null;
  method?: string;
  size?: 'sm' | 'md';
}

export function TranslationBadge({
  isTranslated,
  translationError,
  method,
  size = 'md',
}: TranslationBadgeProps) {
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-0.5 text-xs';

  if (translationError) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full font-medium ${sizeClass} bg-red-50 text-red-700 border border-red-200`}>
        <AlertCircle className="w-3 h-3" />
        Translation unavailable
      </span>
    );
  }

  if (!isTranslated) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full font-medium ${sizeClass} bg-slate-100 text-slate-600 border border-slate-200`}>
        Original
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-medium ${sizeClass} bg-indigo-50 text-indigo-700 border border-indigo-200`}>
      <ArrowRightLeft className="w-3 h-3" />
      Translated
      {method === 'offline_dict' && <span className="opacity-70">(dict)</span>}
    </span>
  );
}

// ─── Multilingual Stats Card ──────────────────────────────────────────────────
interface MultilingualStatsBannerProps {
  stats: MultilingualStats;
}

export function MultilingualStatsBanner({ stats }: MultilingualStatsBannerProps) {
  if (stats.total === 0) return null;

  const hasNonEnglish = stats.kannada > 0 || stats.hindi > 0;

  return (
    <div className="card border-indigo-200 bg-indigo-50/30 animate-in">
      <div className="flex items-start gap-3 mb-4">
        <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0 text-indigo-600">
          <Languages className="w-4 h-4" />
        </div>
        <div>
          <h3 className="font-bold text-slate-900 text-sm">Multilingual Processing</h3>
          <p className="text-slate-500 text-xs mt-0.5">
            Language detection and translation complete
          </p>
        </div>
      </div>

      {/* Language breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Total Reports', value: stats.total, color: 'text-slate-900' },
          { label: 'English',       value: stats.english, color: 'text-blue-600' },
          { label: 'Kannada',       value: stats.kannada, color: 'text-orange-600' },
          { label: 'Hindi',         value: stats.hindi,   color: 'text-green-600' },
        ].map(item => (
          <div key={item.label} className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-center shadow-xs">
            <div className={`text-xl font-bold ${item.color}`}>{item.value}</div>
            <div className="text-xs text-slate-500 font-medium mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Status checklist */}
      <div className="space-y-1.5">
        <StatusLine ok={true} text="Language detected for all reports" />
        <StatusLine ok={hasNonEnglish && stats.translate_enabled}
                    na={!hasNonEnglish}
                    text={
                      !hasNonEnglish
                        ? 'No non-English reports found (no translation needed)'
                        : stats.translate_enabled
                          ? `${stats.translated} non-English report${stats.translated !== 1 ? 's' : ''} translated to English`
                          : 'Translation disabled — original text used'
                    }
        />
        <StatusLine ok={true} text="Ready for SIF analysis via existing NLP pipeline" />
        {stats.translation_errors > 0 && (
          <StatusLine
            ok={false}
            text={`${stats.translation_errors} report${stats.translation_errors !== 1 ? 's' : ''} could not be translated — original text used`}
          />
        )}
      </div>
    </div>
  );
}

function StatusLine({
  ok,
  na,
  text,
}: {
  ok: boolean;
  na?: boolean;
  text: string;
}) {
  if (na) {
    return (
      <div className="flex items-start gap-2 text-xs text-slate-500">
        <span className="flex-shrink-0 mt-0.5">—</span>
        {text}
      </div>
    );
  }
  return (
    <div className={`flex items-start gap-2 text-xs font-medium ${ok ? 'text-green-700' : 'text-red-700'}`}>
      <span className="flex-shrink-0 mt-0.5">{ok ? '✓' : '✗'}</span>
      {text}
    </div>
  );
}

// ─── Inline translation display for report detail / table ─────────────────────
interface TranslationRevealProps {
  originalText: string;
  translatedText: string;
  language: DetectedLanguage;
  isTranslated: boolean;
  translationError?: string | null;
}

export function TranslationReveal({
  originalText,
  translatedText,
  language,
  isTranslated,
  translationError,
}: TranslationRevealProps) {
  if (!isTranslated) {
    return (
      <p className="text-slate-800 text-sm leading-relaxed">{originalText}</p>
    );
  }

  return (
    <div className="space-y-2">
      {/* Original */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg px-3.5 py-2.5">
        <div className="flex items-center gap-2 mb-1">
          <LanguageBadge language={language} size="sm" />
          <span className="text-xs text-slate-500 font-medium">Original</span>
        </div>
        <p className="text-slate-700 text-sm leading-relaxed">{originalText}</p>
      </div>
      {/* Translated */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg px-3.5 py-2.5">
        <div className="flex items-center gap-2 mb-1">
          <LanguageBadge language="en" size="sm" />
          <span className="text-xs text-slate-500 font-medium">Translated (used for analysis)</span>
          {translationError && (
            <span className="text-xs text-red-600 font-semibold flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> {translationError}
            </span>
          )}
        </div>
        <p className="text-slate-900 text-sm leading-relaxed font-medium">{translatedText}</p>
      </div>
    </div>
  );
}

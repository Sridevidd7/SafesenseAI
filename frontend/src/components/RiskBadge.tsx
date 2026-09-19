import { RiskLevel, SIFPotential } from '../types';

interface RiskBadgeProps {
  level: RiskLevel;
  size?: 'sm' | 'md' | 'lg';
}

export function RiskBadge({ level, size = 'md' }: RiskBadgeProps) {
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : size === 'lg' ? 'px-3.5 py-1 text-sm' : 'px-2.5 py-0.5 text-xs';
  const cls: Record<RiskLevel, string> = {
    CRITICAL: 'bg-red-50 text-red-700 border border-red-200',
    HIGH:     'bg-orange-50 text-orange-700 border border-orange-200',
    MEDIUM:   'bg-amber-50 text-amber-700 border border-amber-200',
    LOW:      'bg-green-50 text-green-700 border border-green-200',
  };
  return (
    <span className={`${cls[level]} ${sizeClass} rounded-full font-semibold uppercase tracking-wide inline-flex items-center`}>
      {level}
    </span>
  );
}

interface SIFBadgeProps {
  potential: SIFPotential;
  size?: 'sm' | 'md' | 'lg';
}
export function SIFBadge({ potential, size = 'md' }: SIFBadgeProps) {
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : size === 'lg' ? 'px-3.5 py-1 text-sm' : 'px-2.5 py-0.5 text-xs';
  const cls: Record<SIFPotential, string> = {
    YES:     'bg-red-50 text-red-700 border border-red-200',
    NO:      'bg-green-50 text-green-700 border border-green-200',
    UNKNOWN: 'bg-slate-100 text-slate-600 border border-slate-200',
  };
  return (
    <span className={`${cls[potential]} ${sizeClass} rounded-full font-bold uppercase tracking-wider inline-flex items-center gap-1`}>
      {potential === 'YES' && <span className="w-1.5 h-1.5 rounded-full bg-red-600 inline-block animate-pulse" />}
      SIF: {potential}
    </span>
  );
}

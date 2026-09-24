import { RiskLevel, SIFPotential } from '../types';
import { AlertOctagon, AlertTriangle, ShieldCheck, ShieldAlert, CheckCircle2, HelpCircle } from 'lucide-react';

interface RiskBadgeProps {
  level: RiskLevel | string;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export function RiskBadge({ level, size = 'md', showIcon = true, className = '' }: RiskBadgeProps) {
  const normLevel = (level || 'LOW').toUpperCase() as RiskLevel;

  const sizeClass =
    size === 'sm'
      ? 'px-2 py-0.5 text-[11px]'
      : size === 'lg'
      ? 'px-3 py-1 text-sm'
      : 'px-2.5 py-0.5 text-xs';

  const iconSize = size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-4 h-4' : 'w-3.5 h-3.5';

  const config: Record<RiskLevel, { cls: string; icon: typeof AlertTriangle; label: string }> = {
    CRITICAL: {
      cls: 'bg-red-50 text-red-800 border-red-300 font-bold',
      icon: AlertOctagon,
      label: 'CRITICAL',
    },
    HIGH: {
      cls: 'bg-orange-50 text-orange-800 border-orange-300 font-bold',
      icon: AlertTriangle,
      label: 'HIGH',
    },
    MEDIUM: {
      cls: 'bg-amber-50 text-amber-900 border-amber-300 font-semibold',
      icon: ShieldAlert,
      label: 'MEDIUM',
    },
    LOW: {
      cls: 'bg-emerald-50 text-emerald-800 border-emerald-300 font-medium',
      icon: ShieldCheck,
      label: 'LOW',
    },
  };

  const item = config[normLevel] || config.LOW;
  const Icon = item.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border shadow-2xs ${item.cls} ${sizeClass} uppercase tracking-wider ${className}`}
      aria-label={`Risk Level: ${item.label}`}
    >
      {showIcon && <Icon className={`${iconSize} shrink-0`} aria-hidden="true" />}
      <span>{item.label}</span>
    </span>
  );
}

interface SIFBadgeProps {
  potential: SIFPotential | string;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export function SIFBadge({ potential, size = 'md', showIcon = true, className = '' }: SIFBadgeProps) {
  const normPotential = (potential || 'NO').toUpperCase() as SIFPotential;

  const sizeClass =
    size === 'sm'
      ? 'px-2 py-0.5 text-[11px]'
      : size === 'lg'
      ? 'px-3 py-1 text-sm'
      : 'px-2.5 py-0.5 text-xs';

  const iconSize = size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-4 h-4' : 'w-3.5 h-3.5';

  const config: Record<SIFPotential, { cls: string; icon: typeof AlertTriangle; label: string }> = {
    YES: {
      cls: 'bg-red-100 text-red-900 border-red-300 font-extrabold',
      icon: AlertOctagon,
      label: 'SIF POTENTIAL',
    },
    NO: {
      cls: 'bg-slate-100 text-slate-700 border-slate-300 font-medium',
      icon: CheckCircle2,
      label: 'NON-SIF',
    },
    UNKNOWN: {
      cls: 'bg-slate-100 text-slate-600 border-slate-300 font-normal',
      icon: HelpCircle,
      label: 'SIF UNVERIFIED',
    },
  };

  const item = config[normPotential] || config.UNKNOWN;
  const Icon = item.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border shadow-2xs ${item.cls} ${sizeClass} uppercase tracking-wider ${className}`}
      aria-label={`SIF Classification: ${item.label}`}
    >
      {showIcon && <Icon className={`${iconSize} shrink-0`} aria-hidden="true" />}
      <span>{item.label}</span>
    </span>
  );
}

export default RiskBadge;

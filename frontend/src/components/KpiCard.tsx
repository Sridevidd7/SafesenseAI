import React from 'react';
import { LucideIcon, TrendingUp, TrendingDown, Minus } from 'lucide-react';

export interface KpiCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  variant?: 'blue' | 'red' | 'orange' | 'amber' | 'emerald' | 'indigo' | 'slate';
  trend?: {
    direction: 'up' | 'down' | 'neutral';
    label: string;
    isPositive?: boolean; // Context-aware: e.g. lower SIF is positive (green)
  };
  badge?: string;
  loading?: boolean;
  onClick?: () => void;
  className?: string;
}

const VARIANT_STYLES: Record<string, { border: string; iconBg: string; iconColor: string; badgeBg: string }> = {
  blue: {
    border: 'border-l-blue-600',
    iconBg: 'bg-blue-50',
    iconColor: 'text-blue-700',
    badgeBg: 'bg-blue-50 text-blue-800 border-blue-200',
  },
  red: {
    border: 'border-l-red-600',
    iconBg: 'bg-red-50',
    iconColor: 'text-red-700',
    badgeBg: 'bg-red-50 text-red-800 border-red-200',
  },
  orange: {
    border: 'border-l-orange-500',
    iconBg: 'bg-orange-50',
    iconColor: 'text-orange-700',
    badgeBg: 'bg-orange-50 text-orange-800 border-orange-200',
  },
  amber: {
    border: 'border-l-amber-500',
    iconBg: 'bg-amber-50',
    iconColor: 'text-amber-800',
    badgeBg: 'bg-amber-50 text-amber-900 border-amber-200',
  },
  emerald: {
    border: 'border-l-emerald-600',
    iconBg: 'bg-emerald-50',
    iconColor: 'text-emerald-700',
    badgeBg: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  },
  indigo: {
    border: 'border-l-indigo-600',
    iconBg: 'bg-indigo-50',
    iconColor: 'text-indigo-700',
    badgeBg: 'bg-indigo-50 text-indigo-800 border-indigo-200',
  },
  slate: {
    border: 'border-l-slate-500',
    iconBg: 'bg-slate-100',
    iconColor: 'text-slate-700',
    badgeBg: 'bg-slate-100 text-slate-800 border-slate-200',
  },
};

export default function KpiCard({
  label,
  value,
  subtext,
  icon: Icon,
  variant = 'slate',
  trend,
  badge,
  loading = false,
  onClick,
  className = '',
}: KpiCardProps) {
  const styles = VARIANT_STYLES[variant] || VARIANT_STYLES.slate;

  if (loading) {
    return (
      <div className={`card border-l-4 ${styles.border} flex flex-col justify-between p-4 min-h-[110px] animate-pulse ${className}`}>
        <div className="flex items-start justify-between mb-2">
          <div className="h-3 w-24 bg-slate-200 rounded" />
          <div className="w-8 h-8 rounded-lg bg-slate-200" />
        </div>
        <div className="space-y-1.5">
          <div className="h-7 w-16 bg-slate-200 rounded" />
          <div className="h-2.5 w-32 bg-slate-100 rounded" />
        </div>
      </div>
    );
  }

  const isClickable = Boolean(onClick);

  return (
    <div
      onClick={onClick}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={e => {
        if (isClickable && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick?.();
        }
      }}
      className={`card border-l-4 ${styles.border} flex flex-col justify-between p-4 transition-all duration-150 ${
        isClickable
          ? 'cursor-pointer hover:shadow-md hover:border-slate-300 focus:outline-hidden focus:ring-2 focus:ring-blue-500 focus:ring-offset-1'
          : ''
      } ${className}`}
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">{label}</span>
          {badge && (
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${styles.badgeBg}`}>
              {badge}
            </span>
          )}
        </div>
        {Icon && (
          <div className={`w-8 h-8 rounded-lg ${styles.iconBg} ${styles.iconColor} flex items-center justify-center flex-shrink-0 shadow-2xs`}>
            <Icon className="w-4 h-4" aria-hidden="true" />
          </div>
        )}
      </div>

      <div>
        <div className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight leading-none mb-1.5">
          {value}
        </div>

        <div className="flex items-center justify-between text-xs text-slate-500 font-normal gap-2 flex-wrap">
          {subtext && <span className="truncate">{subtext}</span>}

          {trend && (
            <span
              className={`inline-flex items-center gap-0.5 text-[11px] font-semibold ml-auto ${
                trend.isPositive === undefined
                  ? 'text-slate-600'
                  : trend.isPositive
                  ? 'text-emerald-700'
                  : 'text-red-700'
              }`}
            >
              {trend.direction === 'up' ? (
                <TrendingUp className="w-3 h-3" />
              ) : trend.direction === 'down' ? (
                <TrendingDown className="w-3 h-3" />
              ) : (
                <Minus className="w-3 h-3" />
              )}
              {trend.label}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

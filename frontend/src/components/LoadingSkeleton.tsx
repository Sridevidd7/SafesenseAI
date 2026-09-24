import React from 'react';

export function SkeletonPulse({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-200 rounded-lg ${className}`} />;
}

export function KpiGridSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-4 space-y-3 animate-pulse border-l-4 border-slate-300">
          <div className="flex justify-between items-center">
            <div className="h-3 w-20 bg-slate-200 rounded" />
            <div className="w-7 h-7 bg-slate-200 rounded-lg" />
          </div>
          <div className="h-8 w-16 bg-slate-200 rounded" />
          <div className="h-2.5 w-28 bg-slate-100 rounded" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 'h-72' }: { height?: string }) {
  return (
    <div className={`card p-5 animate-pulse flex flex-col justify-between ${height}`}>
      <div className="flex justify-between items-center mb-4">
        <div className="h-4 w-40 bg-slate-200 rounded" />
        <div className="h-4 w-16 bg-slate-100 rounded" />
      </div>
      <div className="flex-1 bg-slate-100/80 rounded-lg flex items-end gap-3 p-4">
        <div className="w-1/6 bg-slate-200 rounded-t h-1/3" />
        <div className="w-1/6 bg-slate-200 rounded-t h-2/3" />
        <div className="w-1/6 bg-slate-200 rounded-t h-1/2" />
        <div className="w-1/6 bg-slate-200 rounded-t h-4/5" />
        <div className="w-1/6 bg-slate-200 rounded-t h-3/5" />
        <div className="w-1/6 bg-slate-200 rounded-t h-2/5" />
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="card overflow-hidden animate-pulse">
      <div className="p-4 border-b border-slate-200 flex justify-between">
        <div className="h-4 w-32 bg-slate-200 rounded" />
        <div className="h-4 w-20 bg-slate-200 rounded" />
      </div>
      <div className="divide-y divide-slate-100">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-3.5 flex items-center justify-between gap-4">
            <div className="h-3.5 w-16 bg-slate-200 rounded" />
            <div className="h-3.5 flex-1 max-w-md bg-slate-200 rounded" />
            <div className="h-3.5 w-24 bg-slate-100 rounded" />
            <div className="h-5 w-16 bg-slate-200 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default SkeletonPulse;

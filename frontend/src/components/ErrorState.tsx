import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  hint?: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}

export default function ErrorState({
  title = 'Failed to load safety intelligence',
  message = 'An unexpected error occurred while communicating with the SafeSense AI backend.',
  hint = 'Verify that the FastAPI server is running at http://localhost:8000 and has access to safety.db.',
  onRetry,
  retrying = false,
  className = '',
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={`card border-red-300 bg-red-50/70 p-6 flex flex-col sm:flex-row items-start gap-4 text-red-900 shadow-xs ${className}`}
    >
      <div className="w-10 h-10 rounded-xl bg-red-100 border border-red-200 flex items-center justify-center flex-shrink-0 text-red-700">
        <AlertTriangle className="w-5 h-5" aria-hidden="true" />
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="text-sm font-bold text-red-950 mb-1">{title}</h3>
        <p className="text-xs text-red-800 leading-relaxed mb-2">{message}</p>
        {hint && <p className="text-[11px] text-red-700/80 mb-3 font-mono">{hint}</p>}

        {onRetry && (
          <button
            onClick={onRetry}
            disabled={retrying}
            className="btn-secondary text-xs bg-white hover:bg-red-50 text-red-900 border-red-300 disabled:opacity-50 inline-flex items-center gap-2"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${retrying ? 'animate-spin' : ''}`} />
            <span>{retrying ? 'Retrying connection...' : 'Retry Request'}</span>
          </button>
        )}
      </div>
    </div>
  );
}

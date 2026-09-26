import { useNavigate } from 'react-router-dom';
import { Upload, Database } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  message?: string;
  showActions?: boolean;
}

export default function EmptyState({
  title = 'No data available',
  message = 'Upload a CSV file to the backend to start seeing live data. The dashboard, reports, and analytics all reflect real stored records.',
  showActions = true,
}: EmptyStateProps) {
  const navigate = useNavigate();

  return (
    <div className="card flex flex-col items-center justify-center py-20 px-6 text-center">
      <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mb-4">
        <Database className="w-8 h-8 text-slate-400" />
      </div>
      <h3 className="text-xl font-bold text-slate-900 mb-2">{title}</h3>
      <p className="text-slate-500 max-w-md mb-6 text-sm leading-relaxed">{message}</p>
      {showActions && (
        <button onClick={() => navigate('/app/upload')} className="btn-primary">
          <Upload className="w-4 h-4" />
          Upload Dataset
        </button>
      )}
    </div>
  );
}

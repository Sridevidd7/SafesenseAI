import { useState, useEffect, useCallback } from 'react';
import { CheckSquare, Plus, Clock, AlertTriangle, CheckCircle, X, Calendar, User, RefreshCw } from 'lucide-react';
import { fetchActions, createAction, updateAction, ActionItem } from '../services/api';

const STATUS_DISPLAY: Record<string, { label: string; color: string }> = {
  'OPEN':        { label: 'Open',        color: 'text-blue-700 bg-blue-50 border-blue-200' },
  'IN_PROGRESS': { label: 'In Progress', color: 'text-amber-700 bg-amber-50 border-amber-200' },
  'COMPLETED':   { label: 'Completed',   color: 'text-green-700 bg-green-50 border-green-200' },
  'OVERDUE':     { label: 'Overdue',     color: 'text-red-700 bg-red-50 border-red-200' },
};

function formatStatus(status: string) {
  const norm = status.toUpperCase().replace(/\s+/g, '_');
  return STATUS_DISPLAY[norm] || { label: status, color: 'text-slate-700 bg-slate-100 border-slate-200' };
}

interface ActionModalProps {
  onClose: () => void;
  onSave: (payload: { description: string; owner: string; deadline?: string; report_id?: number; status: string }) => Promise<void>;
  saving: boolean;
  error?: string;
}

function ActionModal({ onClose, onSave, saving, error }: ActionModalProps) {
  const [form, setForm] = useState({
    description: '',
    owner: '',
    deadline: '',
    status: 'OPEN',
    report_id: '',
  });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.description || !form.owner) return;
    const reportIdNum = form.report_id.trim() ? parseInt(form.report_id.trim(), 10) : undefined;
    await onSave({
      description: form.description,
      owner: form.owner,
      deadline: form.deadline || undefined,
      report_id: isNaN(reportIdNum as number) ? undefined : reportIdNum,
      status: form.status,
    });
  }

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-bold text-slate-900 text-lg">New Corrective Action</h3>
          <button onClick={onClose} disabled={saving} className="text-slate-400 hover:text-slate-600 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">Action Description *</label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="input-field text-sm min-h-[80px] resize-none"
              placeholder="Describe the corrective action / mitigation plan..."
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">Owner *</label>
              <input
                value={form.owner}
                onChange={e => setForm(f => ({ ...f, owner: e.target.value }))}
                className="input-field text-sm"
                placeholder="Responsible person or team"
                required
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">Status</label>
              <select
                value={form.status}
                onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                className="input-field text-sm"
              >
                <option value="OPEN">Open</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="COMPLETED">Completed</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">Deadline</label>
              <input
                type="date"
                value={form.deadline}
                onChange={e => setForm(f => ({ ...f, deadline: e.target.value }))}
                className="input-field text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">Related Report ID</label>
              <input
                type="number"
                value={form.report_id}
                onChange={e => setForm(f => ({ ...f, report_id: e.target.value }))}
                className="input-field text-sm"
                placeholder="e.g. 12"
              />
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={saving} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button type="submit" disabled={saving || !form.description.trim() || !form.owner.trim()} className="btn-primary flex-1 justify-center">
              {saving ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Saving...
                </>
              ) : 'Save Action'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ActionCenterPage() {
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [modalSaving, setModalSaving] = useState(false);
  const [modalError, setModalError] = useState<string | undefined>(undefined);
  const [filter, setFilter] = useState<string>('ALL');

  const loadActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchActions();
      setActions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch corrective actions from backend.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadActions();
  }, [loadActions]);

  async function handleSaveAction(payload: { description: string; owner: string; deadline?: string; report_id?: number; status: string }) {
    setModalSaving(true);
    setModalError(undefined);
    try {
      const created = await createAction(payload);
      setActions(prev => [created, ...prev]);
      setShowModal(false);
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Failed to save action to database.');
    } finally {
      setModalSaving(false);
    }
  }

  async function handleUpdateStatus(id: number, newStatus: string) {
    try {
      const updated = await updateAction(id, { status: newStatus });
      setActions(prev => prev.map(a => a.id === id ? updated : a));
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update action status.');
    }
  }

  const filtered = filter === 'ALL'
    ? actions
    : actions.filter(a => {
        const norm = (a.status || '').toUpperCase().replace(/\s+/g, '_');
        return norm === filter;
      });

  const stats = {
    open: actions.filter(a => (a.status || '').toUpperCase().includes('OPEN')).length,
    inProgress: actions.filter(a => (a.status || '').toUpperCase().includes('PROGRESS')).length,
    completed: actions.filter(a => (a.status || '').toUpperCase().includes('COMPLETE')).length,
    total: actions.length,
  };

  return (
    <div className="space-y-8 animate-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="section-title">Action Center</h1>
          <p className="section-sub">
            Track and manage corrective actions stored in the database · {actions.length} total actions
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={loadActions} disabled={loading} className="btn-secondary text-sm">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button onClick={() => setShowModal(true)} className="btn-primary">
            <Plus className="w-4 h-4" />
            New Action
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-800 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Backend Connection Issue</p>
            <p className="text-xs text-red-700 mt-0.5">{error}</p>
          </div>
          <button onClick={loadActions} className="btn-secondary text-xs bg-white">Retry</button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Open', value: stats.open, color: 'text-blue-600', icon: CheckSquare, bg: 'border-l-blue-600' },
          { label: 'In Progress', value: stats.inProgress, color: 'text-amber-600', icon: Clock, bg: 'border-l-amber-500' },
          { label: 'Completed', value: stats.completed, color: 'text-green-600', icon: CheckCircle, bg: 'border-l-green-600' },
          { label: 'Total Actions', value: stats.total, color: 'text-slate-800', icon: CheckSquare, bg: 'border-l-slate-500' },
        ].map(s => (
          <div key={s.label} className={`card border-l-4 ${s.bg} p-5`}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{s.label}</span>
              <s.icon className={`w-4 h-4 ${s.color}`} />
            </div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2 flex-wrap">
        {[
          { id: 'ALL', label: 'All' },
          { id: 'OPEN', label: 'Open' },
          { id: 'IN_PROGRESS', label: 'In Progress' },
          { id: 'COMPLETED', label: 'Completed' },
        ].map(f => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              filter === f.id ? 'bg-blue-600 text-white shadow-xs' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Actions List */}
      {loading && actions.length === 0 ? (
        <div className="card text-center py-16 space-y-3">
          <div className="w-6 h-6 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin mx-auto" />
          <p className="text-sm text-slate-500 font-medium">Loading actions from database...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card text-slate-500 text-sm text-center py-16">
          <CheckSquare className="w-10 h-10 text-slate-400 mx-auto mb-3" />
          <p className="font-semibold text-slate-700">
            {filter === 'ALL' ? 'No corrective actions saved yet.' : `No actions with status "${filter}".`}
          </p>
          {filter === 'ALL' && (
            <button onClick={() => setShowModal(true)} className="btn-primary mx-auto mt-4 text-sm">
              <Plus className="w-4 h-4" />Create First Action
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(action => {
            const statusInfo = formatStatus(action.status);
            return (
              <div key={action.id} className="card hover:border-slate-300 p-5 transition-all">
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2.5 mb-2 flex-wrap">
                      <span className="text-xs font-mono text-blue-600 font-semibold bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                        ACT-{action.id}
                      </span>
                      <span className={`text-xs font-semibold border px-2.5 py-0.5 rounded-full ${statusInfo.color}`}>
                        {statusInfo.label}
                      </span>
                      {action.report_id && (
                        <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600 border border-slate-200">
                          Report #{action.report_id}
                        </span>
                      )}
                    </div>
                    <p className="text-sm font-semibold text-slate-900 mb-2 leading-relaxed">
                      {action.description}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-slate-500 flex-wrap">
                      <span className="flex items-center gap-1 font-medium">
                        <User className="w-3.5 h-3.5 text-slate-400" />
                        {action.owner}
                      </span>
                      {action.deadline && (
                        <span className="flex items-center gap-1 font-medium">
                          <Calendar className="w-3.5 h-3.5 text-slate-400" />
                          Deadline: {action.deadline}
                        </span>
                      )}
                      {action.created_at && (
                        <span className="text-slate-400 text-xs">
                          Created: {new Date(action.created_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex-shrink-0">
                    <select
                      value={action.status.toUpperCase().replace(/\s+/g, '_')}
                      onChange={e => handleUpdateStatus(action.id, e.target.value)}
                      className="text-xs bg-white border border-slate-300 text-slate-800 font-medium rounded-lg px-3 py-2 shadow-xs focus:outline-none focus:border-blue-600"
                    >
                      <option value="OPEN">Open</option>
                      <option value="IN_PROGRESS">In Progress</option>
                      <option value="COMPLETED">Completed</option>
                    </select>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showModal && (
        <ActionModal
          onClose={() => setShowModal(false)}
          onSave={handleSaveAction}
          saving={modalSaving}
          error={modalError}
        />
      )}
    </div>
  );
}


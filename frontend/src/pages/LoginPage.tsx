import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Eye, EyeOff, Lock, Mail, AlertCircle } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { User } from '../types';

const DEMO_ACCOUNTS: Array<{ email: string; password: string; user: User }> = [
  { email: 'hse@safesense.ai', password: 'hse123', user: { id: '1', name: 'Alex Morgan', email: 'hse@safesense.ai', role: 'HSE Officer', site: 'Site Alpha' } },
  { email: 'manager@safesense.ai', password: 'mgr123', user: { id: '2', name: 'Jordan Lee', email: 'manager@safesense.ai', role: 'Safety Manager' } },
  { email: 'site@safesense.ai', password: 'site123', user: { id: '3', name: 'Chris Patel', email: 'site@safesense.ai', role: 'Site Manager', site: 'Site Beta' } },
  { email: 'admin@safesense.ai', password: 'admin123', user: { id: '4', name: 'Sam Rivera', email: 'admin@safesense.ai', role: 'Administrator' } },
];

export default function LoginPage() {
  const [email, setEmail] = useState('admin@safesense.ai');
  const [password, setPassword] = useState('admin123');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { dispatch } = useApp();
  const navigate = useNavigate();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    await new Promise(r => setTimeout(r, 600));

    const account = DEMO_ACCOUNTS.find(a => a.email === email && a.password === password);
    if (account) {
      dispatch({ type: 'LOGIN', payload: account.user });
      navigate('/dashboard');
    } else {
      setError('Invalid credentials. Try admin@safesense.ai / admin123');
    }
    setLoading(false);
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md relative z-10">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mb-3 shadow-md shadow-blue-500/20">
            <Shield className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">SafeSense AI</h1>
          <p className="text-slate-500 mt-1 text-sm font-medium">Safety Intelligence Platform</p>
        </div>

        {/* Card */}
        <div className="card shadow-lg p-8">
          <h2 className="text-xl font-bold text-slate-900 mb-1">Sign in to your account</h2>
          <p className="text-slate-500 text-sm mb-6">HSE teams — enter your credentials to continue</p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 mb-1.5 block">Email address</label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="input-field pl-10"
                  placeholder="you@company.com"
                  required
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 mb-1.5 block">Password</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="input-field pl-10 pr-10"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600" />
                {error}
              </div>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-3 mt-2 text-base font-semibold">
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Authenticating...
                </span>
              ) : 'Sign In'}
            </button>
          </form>

          {/* Quick accounts */}
          <div className="mt-8 border-t border-slate-100 pt-5">
            <p className="text-xs text-slate-400 mb-3 font-bold uppercase tracking-wider">Quick demo accounts</p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_ACCOUNTS.map(acc => (
                <button
                  key={acc.email}
                  onClick={() => { setEmail(acc.email); setPassword(acc.password); }}
                  className="text-left p-2.5 rounded-lg bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-200 transition-all"
                >
                  <div className="text-xs font-bold text-slate-800">{acc.user.role}</div>
                  <div className="text-xs text-slate-400 truncate">{acc.email}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-slate-400 mt-6 font-medium">
          SafeSense AI — Enterprise Safety Intelligence Platform
        </p>
      </div>
    </div>
  );
}

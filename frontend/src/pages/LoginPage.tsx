import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Shield, Eye, EyeOff, Lock, Mail, AlertCircle, CheckCircle2, User as UserIcon,
  Building2, ArrowRight, ShieldCheck, Activity, Fingerprint,
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import {
  AuthUser,
  loginAccount,
  registerAccount,
  requestPasswordReset,
  resetPassword,
} from '../services/authClient';

type Mode = 'signin' | 'signup' | 'forgot' | 'reset';

function passwordStrength(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  if (!pw) return { score: 0, label: '' };
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
  const labels = ['Very weak', 'Weak', 'Fair', 'Strong', 'Excellent'];
  return { score: score as 0 | 1 | 2 | 3 | 4, label: labels[score] };
}

const STRENGTH_COLORS = ['bg-slate-200', 'bg-red-500', 'bg-amber-500', 'bg-blue-500', 'bg-emerald-500'];

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isAuthenticated, loading, dispatch } = useApp();

  const [mode, setMode] = useState<Mode>('signin');
  const [name, setName] = useState('');
  const [organization, setOrganization] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [busy, setBusy] = useState(false);

  // Session expired redirect from global 401 handler
  useEffect(() => {
    if (searchParams.get('expired') === '1') {
      setNotice('Your session has expired. Please sign in again.');
    }
  }, [searchParams]);

  useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate('/app/dashboard', { replace: true });
    }
  }, [loading, isAuthenticated, navigate]);

  const strength = useMemo(() => passwordStrength(password), [password]);

  function switchMode(next: Mode) {
    setMode(next);
    setError('');
    setNotice('');
    if (next === 'signin') {
      setPassword('');
      setConfirmPassword('');
    }
  }

  function validate(): boolean {
    if (mode === 'signin') {
      if (!email.trim() || !password) { setError('Enter your email and password.'); return false; }
      return true;
    }
    if (mode === 'signup') {
      if (name.trim().length < 2) { setError('Please enter your full name.'); return false; }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError('Please enter a valid email address.'); return false; }
      if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        setError('Password must be at least 8 characters with letters and numbers.');
        return false;
      }
      if (password !== confirmPassword) { setError('Passwords do not match.'); return false; }
      return true;
    }
    if (mode === 'forgot') {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError('Please enter a valid email address.'); return false; }
      return true;
    }
    // reset
    if (resetToken.trim().length < 16) { setError('Enter the reset token from your administrator or email link.'); return false; }
    if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      setError('Password must be at least 8 characters with letters and numbers.');
      return false;
    }
    if (password !== confirmPassword) { setError('Passwords do not match.'); return false; }
    return true;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setNotice('');
    if (!validate()) return;
    setBusy(true);
    try {
      if (mode === 'signin') {
        const res = await loginAccount(email.trim(), password);
        dispatch({ type: 'LOGIN', payload: { user: res.user as AuthUser, token: res.token } });
        navigate('/app/dashboard');
        return;
      }
      if (mode === 'signup') {
        const res = await registerAccount({
          name: name.trim(),
          email: email.trim(),
          password,
          confirm_password: confirmPassword,
          organization: organization.trim() || undefined,
        });          dispatch({ type: 'LOGIN', payload: { user: res.user as AuthUser, token: res.token } });
          navigate('/app/dashboard');
          return;
      }
      if (mode === 'forgot') {
        const res = await requestPasswordReset(email.trim());
        if (res.dev_reset_token) {
          // Local development only: the backend explicitly exposes this token
          // under SAFESENSE_DEV_EXPOSE_RESET_TOKEN=1 when email is unconfigured.
          setResetToken(res.dev_reset_token);
          setMode('reset');
          setNotice('Email delivery is not configured in this environment. Use the development reset token below.');
        } else {
          setNotice(res.message || 'If an account exists for that address, a password reset link has been sent.');
          setMode('signin');
        }
        return;
      }
      // mode === 'reset'
      const res = await resetPassword({ token: resetToken.trim(), password, confirm_password: confirmPassword });
      dispatch({ type: 'LOGIN', payload: { user: res.user as AuthUser, token: res.token } });
      navigate('/app/dashboard');
      return;
    } catch (err) {
      setError((err as Error).message || 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 relative overflow-hidden flex items-center justify-center px-4 py-12">
      {/* Ambient industrial background */}
      <div aria-hidden className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(37,99,235,0.16),transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,rgba(16,185,129,0.08),transparent_50%)]" />
        <svg className="absolute inset-0 w-full h-full opacity-[0.05]" aria-hidden>
          <defs>
            <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">
              <path d="M 44 0 L 0 0 0 44" fill="none" stroke="white" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      <div className="w-full max-w-md relative z-10">
        {/* Brand */}
        <div className="flex flex-col items-center mb-8 text-center">
          <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-blue-600/30">
            <Shield className="w-8 h-8 text-white" aria-hidden />
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">SafeSense AI</h1>
          <p className="text-slate-400 mt-1.5 text-sm font-medium">Industrial Safety Intelligence Platform</p>
        </div>

        {/* Card */}
        <div className="bg-white/95 backdrop-blur border border-slate-200 rounded-2xl shadow-2xl p-8">
          {mode === 'signin' && (
            <>
              <h2 className="text-xl font-bold text-slate-900 mb-1">Sign in</h2>
              <p className="text-slate-500 text-sm mb-6">Access your organization's safety intelligence workspace.</p>
            </>
          )}
          {mode === 'signup' && (
            <>
              <h2 className="text-xl font-bold text-slate-900 mb-1">Create account</h2>
              <p className="text-slate-500 text-sm mb-6">Set up your SafeSense AI workspace access.</p>
            </>
          )}
          {mode === 'forgot' && (
            <>
              <h2 className="text-xl font-bold text-slate-900 mb-1">Reset password</h2>
              <p className="text-slate-500 text-sm mb-6">Enter your account email to request a reset link.</p>
            </>
          )}
          {mode === 'reset' && (
            <>
              <h2 className="text-xl font-bold text-slate-900 mb-1">Set a new password</h2>
              <p className="text-slate-500 text-sm mb-6">Enter the reset token you received and choose a new password.</p>
            </>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {mode === 'signup' && (
              <>
                <div>
                  <label htmlFor="auth-name" className="text-xs font-semibold text-slate-700 mb-1.5 block">Full name</label>
                  <div className="relative">
                    <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden />
                    <input id="auth-name" type="text" value={name} onChange={e => setName(e.target.value)}
                      className="input-field pl-10" placeholder="Jane Doe" autoComplete="name" required />
                  </div>
                </div>
                <div>
                  <label htmlFor="auth-org" className="text-xs font-semibold text-slate-700 mb-1.5 block">
                    Organization <span className="text-slate-400 font-normal">(optional)</span>
                  </label>
                  <div className="relative">
                    <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden />
                    <input id="auth-org" type="text" value={organization} onChange={e => setOrganization(e.target.value)}
                      className="input-field pl-10" placeholder="Company or site name" autoComplete="organization" />
                  </div>
                </div>
              </>
            )}

            {mode !== 'reset' && (
              <div>
                <label htmlFor="auth-email" className="text-xs font-semibold text-slate-700 mb-1.5 block">Email address</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden />
                  <input id="auth-email" type="email" value={email} onChange={e => setEmail(e.target.value)}
                    className="input-field pl-10" placeholder="you@company.com" autoComplete="email" required />
                </div>
              </div>
            )}

            {mode === 'reset' && (
              <div>
                <label htmlFor="auth-reset-token" className="text-xs font-semibold text-slate-700 mb-1.5 block">Reset token</label>
                <div className="relative">
                  <Fingerprint className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden />
                  <input id="auth-reset-token" type="text" value={resetToken} onChange={e => setResetToken(e.target.value)}
                    className="input-field pl-10 font-mono text-xs" placeholder="Paste your reset token" autoComplete="one-time-code" required />
                </div>
              </div>
            )}

            {(mode === 'signin' || mode === 'signup' || mode === 'reset') && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label htmlFor="auth-password" className="text-xs font-semibold text-slate-700">
                    {mode === 'reset' ? 'New password' : 'Password'}
                  </label>
                  {mode === 'signin' && (
                    <button type="button" onClick={() => switchMode('forgot')}
                      className="text-xs font-medium text-blue-600 hover:text-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded">
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden />
                  <input id="auth-password" type={showPass ? 'text' : 'password'} value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="input-field pl-10 pr-10" placeholder="••••••••"
                    autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} required />
                  <button type="button" onClick={() => setShowPass(!showPass)}
                    aria-label={showPass ? 'Hide password' : 'Show password'}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded">
                    {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {mode !== 'signin' && password && (
                  <div className="mt-2" aria-live="polite">
                    <div className="flex gap-1.5">
                      {[0, 1, 2, 3].map(i => (
                        <div key={i} className={`h-1 flex-1 rounded-full ${i < strength.score ? STRENGTH_COLORS[strength.score] : 'bg-slate-200'}`} />
                      ))}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">Password strength: {strength.label}</p>
                  </div>
                )}
              </div>
            )}

            {(mode === 'signup' || mode === 'reset') && (
              <div>
                <label htmlFor="auth-confirm" className="text-xs font-semibold text-slate-700 mb-1.5 block">Confirm password</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden />
                  <input id="auth-confirm" type={showPass ? 'text' : 'password'} value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    className="input-field pl-10" placeholder="••••••••"
                    autoComplete="new-password" required />
                </div>
              </div>
            )}

            {error && (
              <div role="alert" className="flex items-start gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600 mt-0.5" aria-hidden />
                {error}
              </div>
            )}
            {notice && !error && (
              <div role="status" className="flex items-start gap-2 text-blue-700 bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-blue-600 mt-0.5" aria-hidden />
                {notice}
              </div>
            )}

            <button type="submit" disabled={busy}
              className="btn-primary w-full justify-center py-3 mt-2 text-base font-semibold">
              {busy ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" aria-hidden />
                  {mode === 'signin' && 'Signing in…'}
                  {mode === 'signup' && 'Creating account…'}
                  {mode === 'forgot' && 'Sending request…'}
                  {mode === 'reset' && 'Updating password…'}
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  {mode === 'signin' && <>Sign in <ArrowRight className="w-4 h-4" aria-hidden /></>}
                  {mode === 'signup' && <>Create account</>}
                  {mode === 'forgot' && <>Send reset request</>}
                  {mode === 'reset' && <>Set new password</>}
                </span>
              )}
            </button>
          </form>

          {/* Mode switch */}
          <div className="mt-6 text-center text-sm">
            {mode === 'signin' && (
              <p className="text-slate-500">
                New to SafeSense AI?{' '}
                <button type="button" onClick={() => switchMode('signup')}
                  className="font-semibold text-blue-600 hover:text-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded">
                  Create an account
                </button>
              </p>
            )}
            {mode !== 'signin' && (
              <button type="button" onClick={() => switchMode('signin')}
                className="font-semibold text-blue-600 hover:text-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded">
                ← Back to sign in
              </button>
            )}
          </div>
        </div>

        {/* Trust markers */}
        <div className="flex items-center justify-center gap-6 mt-8 text-xs text-slate-500 font-medium">
          <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden /> AI-assisted. Evidence-grounded.</span>
          <span className="hidden sm:flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-blue-400" aria-hidden /> Human-authorized</span>
        </div>
      </div>
    </div>
  );
}

import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  Shield, LayoutDashboard, Upload, Brain, TrendingUp, GitBranch,
  MapPin, CheckSquare, MessageSquare, FileText, Settings, Menu, X,
  LogOut, Bell, ChevronRight, Command, User
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { logoutOnServer, fetchPlatformInfo } from '../services/authClient';
import { useState, useEffect } from 'react';

const NAV_ITEMS = [
  { to: '/app/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/upload', icon: Upload, label: 'Upload Reports' },
  { to: '/app/analysis', icon: Brain, label: 'AI Analysis' },
  { to: '/app/risk-intelligence', icon: TrendingUp, label: 'Risk Intelligence' },
  { to: '/app/patterns', icon: GitBranch, label: 'Safety Patterns' },
  { to: '/app/sites', icon: MapPin, label: 'Sites & Activities' },
  { to: '/app/actions', icon: CheckSquare, label: 'Action Center' },
  { to: '/app/copilot', icon: MessageSquare, label: 'Safety Copilot' },
  { to: '/app/reports', icon: FileText, label: 'Reports' },
  { to: '/app/command-center', icon: Command, label: 'Command Center' },
  { to: '/app/settings', icon: Settings, label: 'Settings' },
];

export default function Layout() {
  const { user, dispatch, sidebarOpen, dataset, isDemo } = useApp();
  const navigate = useNavigate();
  const [notifOpen, setNotifOpen] = useState(false);
  const [platformLabel, setPlatformLabel] = useState<string | null>(null);

  useEffect(() => {
    fetchPlatformInfo().then(info => {
      if (info) setPlatformLabel(`${info.database} · ${info.vector_store}`);
    });
  }, []);

  function handleLogout() {
    // Server-verified logout first (revocation contract), then local discard.
    const token = getStoredTokenSafe();
    if (token) {
      logoutOnServer(token);
    }
    dispatch({ type: 'LOGOUT' });
    navigate('/login');
  }

  function getStoredTokenSafe(): string | null {
    try {
      return localStorage.getItem('safesense_token');
    } catch {
      return null;
    }
  }

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      {/* Sidebar */}
      <aside
        className={`flex flex-col bg-white border-r border-slate-200 transition-all duration-300 flex-shrink-0 z-20 ${
          sidebarOpen ? 'w-64' : 'w-16'
        }`}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-5 border-b border-slate-200">
          <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-sm">
            <Shield className="w-5 h-5 text-white" />
          </div>
          {sidebarOpen && (
            <div className="overflow-hidden">
              <div className="font-bold text-slate-900 text-base leading-tight">SafeSense AI</div>
              <div className="text-xs font-medium text-blue-600 truncate">Safety Intelligence</div>
            </div>
          )}
        </div>

        {/* Dataset status */}
        {sidebarOpen && dataset && (
          <div className={`mx-3 mt-3 px-3 py-2 rounded-lg text-xs font-medium ${isDemo ? 'bg-amber-50 border border-amber-200 text-amber-800' : 'bg-green-50 border border-green-200 text-green-800'}`}>
            {isDemo ? '⚠ Demo Data Active' : `✓ ${dataset.rows} reports loaded`}
          </div>
        )}

        {/* Platform runtime label — dynamic from backend metadata */}
        {sidebarOpen && platformLabel && (
          <div className="mx-3 mt-2 px-3 py-2 rounded-lg text-[11px] font-medium text-slate-500 bg-slate-50 border border-slate-200" title="Runtime platform (from backend metadata)">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5" aria-hidden />
            {platformLabel}
          </div>
        )}

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto py-3 space-y-1 px-2">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group ${
                  isActive
                    ? 'bg-blue-50 text-blue-600 font-semibold shadow-xs'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {sidebarOpen && <span className="truncate">{label}</span>}
              {sidebarOpen && (
                <ChevronRight className="w-3.5 h-3.5 ml-auto opacity-0 group-hover:opacity-60 transition-opacity" />
              )}
            </NavLink>
          ))}
        </nav>

        {/* User section */}
        {sidebarOpen && user && (
          <div className="border-t border-slate-200 p-3 bg-slate-50/50">
            <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-slate-100 cursor-pointer transition-colors" onClick={handleLogout}>
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 text-xs font-bold flex-shrink-0">
                {user.name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-800 truncate">{user.name}</div>
                <div className="text-xs text-slate-500 truncate">{user.role}</div>
              </div>
              <LogOut className="w-4 h-4 text-slate-400 hover:text-slate-600 flex-shrink-0" />
            </div>
          </div>
        )}
      </aside>

      {/* Main area */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Topbar */}
        <header className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-200 flex-shrink-0 z-10">
          <div className="flex items-center gap-3">
            <button
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition-colors"
            >
              {sidebarOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
            {isDemo && (
              <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 rounded-full font-medium">
                ⚠ Synthetic Demo Data — Not Real Organizational Data
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <button
                onClick={() => setNotifOpen(!notifOpen)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition-colors relative"
              >
                <Bell className="w-4 h-4" />
                <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"></span>
              </button>
            </div>
            {user && (
              <div className="flex items-center gap-2 text-sm text-slate-600 bg-slate-100 px-3 py-1.5 rounded-full">
                <User className="w-3.5 h-3.5 text-slate-500" />
                <span className="hidden sm:inline font-medium text-xs text-slate-700">{user.role}</span>
              </div>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-slate-50">
          <div className="max-w-7xl mx-auto p-6 md:p-8 min-h-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

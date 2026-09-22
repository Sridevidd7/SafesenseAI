import React, { createContext, useContext, useReducer, useEffect, ReactNode } from 'react';
import { SafetyReport, DatasetInfo, User, CorrectiveAction, MultilingualStats, EMPTY_MULTILINGUAL_STATS } from '../types';

// ─── State ────────────────────────────────────────────────────────────────────
interface AppState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  dataset: DatasetInfo | null;
  reports: SafetyReport[];
  selectedReport: SafetyReport | null;
  actions: CorrectiveAction[];
  sidebarOpen: boolean;
  isDemo: boolean;
  multilingualStats: MultilingualStats;
  translateEnabled: boolean;
}

const initialState: AppState = {
  user: null,
  token: null,
  isAuthenticated: false,
  loading: true,
  dataset: null,
  reports: [],
  selectedReport: null,
  actions: [],
  sidebarOpen: true,
  isDemo: false,
  multilingualStats: { ...EMPTY_MULTILINGUAL_STATS },
  translateEnabled: true,
};

// ─── Actions ──────────────────────────────────────────────────────────────────
type Action =
  | { type: 'LOGIN'; payload: User }
  | { type: 'RESTORE_AUTH'; payload: { user: User; token: string } }
  | { type: 'AUTH_READY' }
  | { type: 'LOGOUT' }
  | { type: 'SET_DATASET'; payload: { dataset: DatasetInfo; reports: SafetyReport[]; isDemo: boolean; multilingualStats?: MultilingualStats } }
  | { type: 'CLEAR_DATASET' }
  | { type: 'UPDATE_REPORT'; payload: SafetyReport }
  | { type: 'SET_SELECTED_REPORT'; payload: SafetyReport | null }
  | { type: 'ADD_ACTION'; payload: CorrectiveAction }
  | { type: 'UPDATE_ACTION'; payload: CorrectiveAction }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_SIDEBAR'; payload: boolean }
  | { type: 'SET_TRANSLATE_ENABLED'; payload: boolean }
  | { type: 'SET_MULTILINGUAL_STATS'; payload: MultilingualStats };

function appReducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'LOGIN': {
      const user = action.payload;
      const token = user.token || localStorage.getItem('token') || `token_${user.id}_${Date.now()}`;
      try {
        localStorage.setItem('token', token);
        localStorage.setItem('user', JSON.stringify({ ...user, token }));
      } catch (e) {
        console.error('Failed to persist user in localStorage:', e);
      }
      return {
        ...state,
        user: { ...user, token },
        token,
        isAuthenticated: true,
        loading: false,
      };
    }
    case 'RESTORE_AUTH': {
      return {
        ...state,
        user: action.payload.user,
        token: action.payload.token,
        isAuthenticated: true,
        loading: false,
      };
    }
    case 'AUTH_READY': {
      return {
        ...state,
        loading: false,
      };
    }
    case 'LOGOUT': {
      try {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      } catch (e) {
        console.error('Failed to clear localStorage on logout:', e);
      }
      return { ...initialState, loading: false };
    }
    case 'SET_DATASET':
      return {
        ...state,
        dataset: action.payload.dataset,
        reports: action.payload.reports,
        isDemo: action.payload.isDemo,
        multilingualStats: action.payload.multilingualStats ?? computeStatsFromReports(action.payload.reports),
      };
    case 'CLEAR_DATASET':
      return { ...state, dataset: null, reports: [], isDemo: false, multilingualStats: { ...EMPTY_MULTILINGUAL_STATS } };
    case 'UPDATE_REPORT':
      return {
        ...state,
        reports: state.reports.map(r =>
          r.id === action.payload.id ? action.payload : r
        ),
        selectedReport:
          state.selectedReport?.id === action.payload.id
            ? action.payload
            : state.selectedReport,
      };
    case 'SET_SELECTED_REPORT':
      return { ...state, selectedReport: action.payload };
    case 'ADD_ACTION':
      return { ...state, actions: [...state.actions, action.payload] };
    case 'UPDATE_ACTION':
      return {
        ...state,
        actions: state.actions.map(a =>
          a.id === action.payload.id ? action.payload : a
        ),
      };
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case 'SET_SIDEBAR':
      return { ...state, sidebarOpen: action.payload };
    case 'SET_TRANSLATE_ENABLED':
      return { ...state, translateEnabled: action.payload };
    case 'SET_MULTILINGUAL_STATS':
      return { ...state, multilingualStats: action.payload };
    default:
      return state;
  }
}

/** Derive multilingual stats from reports array (used for demo data) */
function computeStatsFromReports(reports: SafetyReport[]): MultilingualStats {
  const stats = { ...EMPTY_MULTILINGUAL_STATS, total: reports.length, translate_enabled: true };
  for (const r of reports) {
    switch (r.detected_language) {
      case 'en':      stats.english++;  break;
      case 'kn':      stats.kannada++;  break;
      case 'hi':      stats.hindi++;    break;
      default:        stats.english++;  break; // demo data is English
    }
    if (r.is_translated)     stats.translated++;
    if (r.translation_error) stats.translation_errors++;
  }
  return stats;
}

// ─── Context ─────────────────────────────────────────────────────────────────
interface AppContextValue extends AppState {
  dispatch: React.Dispatch<Action>;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  // Rehydrate auth state on mount before any routing decisions
  useEffect(() => {
    try {
      const token = localStorage.getItem('token');
      const storedUser = localStorage.getItem('user');

      console.log('TOKEN:', token);
      console.log('USER STATE:', storedUser ? JSON.parse(storedUser) : null);

      if (token && storedUser) {
        const parsedUser = JSON.parse(storedUser) as User;
        dispatch({ type: 'RESTORE_AUTH', payload: { user: parsedUser, token } });
      } else if (token) {
        const defaultUser: User = {
          id: '1',
          name: 'Alex Morgan',
          email: 'hse@safesense.ai',
          role: 'HSE Officer',
          site: 'Site Alpha',
          token,
        };
        localStorage.setItem('user', JSON.stringify(defaultUser));
        dispatch({ type: 'RESTORE_AUTH', payload: { user: defaultUser, token } });
      } else {
        dispatch({ type: 'AUTH_READY' });
      }
    } catch (err) {
      console.error('Error rehydrating auth state:', err);
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      dispatch({ type: 'AUTH_READY' });
    }
  }, []);

  // Debug logging
  useEffect(() => {
    console.log('LOADING:', state.loading);
    console.log('USER STATE:', state.user);
  }, [state.loading, state.user]);

  return (
    <AppContext.Provider value={{ ...state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}

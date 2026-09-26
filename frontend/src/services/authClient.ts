/**
 * authClient.ts — Real backend authentication client.
 *
 * All authentication goes through the FastAPI backend:
 *   POST /api/auth/register         → create account (bcrypt on server)
 *   POST /api/auth/login            → credential login (JWT issued)
 *   GET  /api/auth/me               → session resolution / restoration
 *   POST /api/auth/logout           → server-verified logout contract
 *   POST /api/auth/forgot-password  → request reset (no account enumeration)
 *   POST /api/auth/reset-password   → consume reset token
 *   GET  /api/auth/platform-info    → dynamic runtime labels (non-sensitive)
 *
 * No tokens are generated in the browser. The JWT is issued by the backend,
 * persisted in localStorage, and re-validated against /api/auth/me on
 * restoration. Expired/invalid/revoked tokens are cleared automatically.
 */

import { getApiUrl } from './api';

export interface AuthUser {
  id: number;
  email: string;
  name: string;
  role: string;
  organization?: string | null;
  site?: string | null;
  is_active?: boolean;
}

export interface AuthResponse {
  token: string;
  token_type: string;
  expires_in_minutes: number;
  user: AuthUser;
}

export interface PlatformInfo {
  database: string;
  vector_store: string;
  environment: string;
  version: string;
}

const TOKEN_KEY = 'safesense_token';
const USER_KEY = 'safesense_user';

// ─── Token storage ────────────────────────────────────────────────────────────

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function storeSession(token: string, user: AuthUser): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    // storage unavailable — session stays memory-only
  }
}

export function clearStoredSession(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    // Legacy keys from the previous demo-auth implementation
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  } catch {
    // ignore
  }
}

function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

// ─── Request helper ───────────────────────────────────────────────────────────

async function authFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // getApiUrl() honors VITE_API_BASE_URL (split-origin Render deployment).
  const res = await fetch(getApiUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string> || {}),
    },
  });
  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch {
      // ignore
    }
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

// ─── API operations ───────────────────────────────────────────────────────────

export async function registerAccount(payload: {
  name: string;
  email: string;
  password: string;
  confirm_password: string;
  organization?: string;
}): Promise<AuthResponse> {
  return authFetch<AuthResponse>('/auth/register', { method: 'POST', body: JSON.stringify(payload) });
}

export async function loginAccount(email: string, password: string): Promise<AuthResponse> {
  return authFetch<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export async function fetchCurrentUser(token: string): Promise<AuthUser> {
  return authFetch<AuthUser>('/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function logoutOnServer(token: string): Promise<void> {
  try {
    await authFetch<{ status: string }>('/auth/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Token already invalid — local discard is still the correct behavior.
  }
}

export async function requestPasswordReset(email: string): Promise<{ message: string; dev_reset_token?: string | null }> {
  return authFetch('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) });
}

export async function resetPassword(payload: {
  token: string;
  password: string;
  confirm_password: string;
}): Promise<AuthResponse> {
  return authFetch<AuthResponse>('/auth/reset-password', { method: 'POST', body: JSON.stringify(payload) });
}

export async function fetchPlatformInfo(): Promise<PlatformInfo | null> {
  try {
    return await authFetch<PlatformInfo>('/auth/platform-info');
  } catch {
    return null; // never block the UI on metadata
  }
}

export interface SessionValidation {
  user: AuthUser;
  token: string;
}

/**
 * Restore and re-validate a persisted session against the backend.
 * Returns null when no session exists or the token is invalid/expired/revoked
 * (in which case the stored token is cleared).
 */
export async function restoreSession(): Promise<SessionValidation | null> {
  const token = getStoredToken();
  if (!token) return null;
  try {
    const user = await fetchCurrentUser(token);
    storeSession(token, user); // refresh cached profile (role may have changed)
    return { user, token };
  } catch (err) {
    const status = (err as { status?: number })?.status;
    if (status === 401 || status === 403) {
      clearStoredSession();
    }
    return null;
  }
}

export { getStoredUser };

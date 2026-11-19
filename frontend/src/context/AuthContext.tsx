import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  authApi,
  clearTokens,
  getAccessToken,
  getStoredUser,
  setStoredUser,
  setTokens,
  UNAUTHORIZED_EVENT,
  type RequestOptions,
} from '../lib/api';
import type { LoginOptions, TokenPair, User } from '../types';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string, options?: LoginOptions) => Promise<{ user: User; session: TokenPair }>;
  register: (payload: {
    email: string;
    password: string;
    full_name: string;
    organisation?: string;
    consent_privacy: boolean;
    consent_terms: boolean;
  }) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => getStoredUser());
  const [loading, setLoading] = useState(() => !!getAccessToken());

  const logoutLocal = useCallback(() => {
    clearTokens();
    setUser(null);
    setLoading(false);
  }, []);

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) return;
    try {
      const me = await authApi.me();
      setUser(me);
      setStoredUser(me);
    } catch {
      logoutLocal();
    }
  }, [logoutLocal]);

  useEffect(() => {
    if (getAccessToken()) void refreshUser().finally(() => setLoading(false));
    else setLoading(false);
    window.addEventListener(UNAUTHORIZED_EVENT, logoutLocal);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, logoutLocal);
  }, [refreshUser, logoutLocal]);

  const login = useCallback(async (email: string, password: string, options: LoginOptions = {}) => {
    const session: TokenPair = await authApi.login(email, password, options);
    setTokens(session);
    const me = await authApi.me().catch(() => undefined);
    const nextUser: User =
      me ??
      ({
        id: 'unknown',
        email,
        full_name: email.split('@')[0],
        role: 'user',
        created_at: new Date().toISOString(),
      } as User);
    setUser(nextUser);
    setStoredUser(nextUser);
    setLoading(false);
    return { user: nextUser, session };
  }, []);

  const register = useCallback<AuthContextValue['register']>(async (payload) => {
    const created = await authApi.register(payload);
    setStoredUser(created);
    return created;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Local logout succeeds even if the server rejects the token.
    }
    logoutLocal();
  }, [logoutLocal]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: !!getAccessToken() && !!user,
      isAdmin: user?.role === 'admin' || user?.role === 'owner',
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

/** Convenience for components that need a plain request wrapper. */
export type { RequestOptions };

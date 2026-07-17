import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AUTH_LOGOUT_EVENT,
  authService,
  clearStoredAuth,
  getStoredAccessToken,
  getStoredRefreshToken,
  persistAuthTokens,
  type AuthTokens,
  type RegisterPayload,
} from '@/services/api';

export interface UserProfile {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

interface AuthContextValue {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName: string, lastName: string) => Promise<void>;
  logout: () => Promise<void>;
}

interface JwtPayload {
  user_id?: number;
  email?: string;
  first_name?: string;
  last_name?: string;
  exp?: number;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const readStoredUser = (): UserProfile | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const storedUser = window.localStorage.getItem('user');
  if (!storedUser) {
    return null;
  }

  try {
    const parsedUser = JSON.parse(storedUser) as UserProfile;
    return parsedUser;
  } catch {
    return null;
  }
};

const persistStoredUser = (user: UserProfile): void => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('user', JSON.stringify(user));
  }
};

const decodeJwtPayload = (token: string): JwtPayload => {
  const payload = token.split('.')[1];
  if (!payload) {
    return {};
  }

  const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
  const decoded = globalThis.atob(normalized);
  return JSON.parse(decoded) as JwtPayload;
};

const isTokenValidSync = (): boolean => {
  const token = getStoredAccessToken();
  if (!token) return false;
  try {
    const payload = decodeJwtPayload(token);
    if (payload.exp && payload.exp * 1000 > Date.now()) {
      return true;
    }
  } catch {
    return false;
  }
  return false;
};

const buildUserFromTokens = (tokens: AuthTokens): UserProfile | null => {
  const accessToken = tokens.access;
  if (!accessToken) {
    return null;
  }

  const payload = decodeJwtPayload(accessToken);
  return {
    id: payload.user_id ?? 0,
    email: payload.email ?? '',
    first_name: payload.first_name ?? '',
    last_name: payload.last_name ?? '',
  };
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<UserProfile | null>(() => {
    const stored = readStoredUser();
    if (stored && isTokenValidSync()) {
      return stored;
    }
    return null;
  });
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => isTokenValidSync());
  const [isLoading, setIsLoading] = useState<boolean>(() => !isTokenValidSync() && Boolean(getStoredRefreshToken()));

  const restoreSession = useCallback(async (): Promise<void> => {
    // If the token is already valid synchronously, skip async refresh on load
    if (isTokenValidSync()) {
      setIsLoading(false);
      return;
    }

    const refreshToken = getStoredRefreshToken();
    if (!refreshToken) {
      setUser(null);
      setIsAuthenticated(false);
      setIsLoading(false);
      return;
    }

    try {
      const tokens = await authService.refresh(refreshToken);
      persistAuthTokens(tokens);
      const nextUser = buildUserFromTokens(tokens);
      if (nextUser) {
        persistStoredUser(nextUser);
      }
      setUser(nextUser);
      setIsAuthenticated(Boolean(nextUser));
    } catch {
      clearStoredAuth();
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<void> => {
    setIsLoading(true);
    try {
      const tokens = await authService.login({ email, password });
      if (!tokens.access || !tokens.refresh) {
        throw new Error('The server did not return valid authentication tokens.');
      }
      persistAuthTokens(tokens);
      const nextUser = buildUserFromTokens(tokens);
      if (nextUser) {
        persistStoredUser(nextUser);
      }
      setUser(nextUser);
      setIsAuthenticated(Boolean(nextUser));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const register = useCallback(async (email: string, password: string, firstName: string, lastName: string): Promise<void> => {
    setIsLoading(true);
    try {
      const payload: RegisterPayload = {
        email,
        password,
        first_name: firstName || undefined,
        last_name: lastName || undefined,
      };

      await authService.register(payload);
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    clearStoredAuth();
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  useEffect(() => {
    void restoreSession();

    const handleLogout = (): void => {
      setUser(null);
      setIsAuthenticated(false);
    };

    window.addEventListener(AUTH_LOGOUT_EVENT, handleLogout);
    return () => {
      window.removeEventListener(AUTH_LOGOUT_EVENT, handleLogout);
    };
  }, [restoreSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated,
      isLoading,
      login,
      register,
      logout,
    }),
    [user, isAuthenticated, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

import axios, { type AxiosError, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios';

const resolveApiBaseUrl = (): string => {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.endsWith('/') ? configured : `${configured}/`;
  }

  return 'http://127.0.0.1:8000/api/';
};

export const API_BASE_URL = resolveApiBaseUrl();
export const ACCESS_TOKEN_STORAGE_KEY = 'access_token';
export const REFRESH_TOKEN_STORAGE_KEY = 'refresh_token';
export const AUTH_LOGOUT_EVENT = 'auth:logout';

export interface AuthTokens {
  access: string;
  refresh: string;
}

interface TokenResponseShape {
  access?: string;
  refresh?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export interface RegisterResponse {
  message: string;
  user: {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
  };
}

export interface TrackedProduct {
  id: number;
  product_name: string;
  target_url: string;
  notification_threshold: number;
  current_price?: number | string;
  is_active: boolean;
  created_at: string;
  last_scraped_at: string | null;
  domain_name: string;
  price_histories: Array<{
    id: number;
    price: number;
    is_available: boolean;
    scraped_at: string;
  }>;
}

export interface AnalyticsSummary {
  tracker_count: number;
  active_trackers: number;
  history_points: number;
  latest_prices: Array<{
    product_id: number;
    product_name: string;
    current_price: string;
    last_scraped_at: string;
    is_active: boolean;
  }>;
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const getStoredValue = (key: string): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage.getItem(key);
};

const setStoredValue = (key: string, value: string): void => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(key, value);
  }
};

const removeStoredValue = (key: string): void => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(key);
  }
};

const normalizeTokenResponse = (payload: TokenResponseShape): AuthTokens => ({
  access: payload.access ?? '',
  refresh: payload.refresh ?? '',
});

export const persistAuthTokens = (tokens: AuthTokens): void => {
  setStoredValue(ACCESS_TOKEN_STORAGE_KEY, tokens.access);
  setStoredValue(REFRESH_TOKEN_STORAGE_KEY, tokens.refresh);
};

export const clearStoredAuth = (): void => {
  removeStoredValue(ACCESS_TOKEN_STORAGE_KEY);
  removeStoredValue(REFRESH_TOKEN_STORAGE_KEY);
  removeStoredValue('user');
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  }
};

export const getStoredAccessToken = (): string | null => getStoredValue(ACCESS_TOKEN_STORAGE_KEY);
export const getStoredRefreshToken = (): string | null => getStoredValue(REFRESH_TOKEN_STORAGE_KEY);

api.interceptors.request.use((config) => {
  const token = getStoredAccessToken();
  if (token) {
    const headers = config.headers ?? {};
    (headers as Record<string, string>).Authorization = `Bearer ${token}`;
    config.headers = headers;
  }
  return config;
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token!);
    }
  });
  failedQueue = [];
};

const refreshAccessToken = async (): Promise<void> => {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) {
    throw new Error('Missing refresh token');
  }

  const response = await api.post<TokenResponseShape>('auth/refresh/', { refresh: refreshToken });
  const tokens = normalizeTokenResponse(response.data);
  if (!tokens.access || !tokens.refresh) {
    throw new Error('Refresh response did not include valid tokens');
  }
  persistAuthTokens(tokens);
};

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean });

    // Handle token refresh failures (401 or 403 on /auth/refresh/)
    if (originalRequest && originalRequest.url?.includes('/auth/refresh/')) {
      if (error.response?.status === 401 || error.response?.status === 403) {
        clearStoredAuth();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    }

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/refresh/')
    ) {
      originalRequest._retry = true;

      if (isRefreshing) {
        return new Promise<AxiosResponse>((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              const headers = originalRequest.headers ?? {};
              (headers as Record<string, string>).Authorization = `Bearer ${token}`;
              originalRequest.headers = headers;
              resolve(api(originalRequest));
            },
            reject: (err: any) => {
              reject(err);
            },
          });
        });
      }

      isRefreshing = true;

      const refreshToken = getStoredRefreshToken();
      if (!refreshToken) {
        clearStoredAuth();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        return Promise.reject(new Error('Missing refresh token'));
      }

      try {
        await refreshAccessToken();
        const token = getStoredAccessToken();
        if (!token) {
          throw new Error('New access token missing');
        }
        processQueue(null, token);
        const headers = originalRequest.headers ?? {};
        (headers as Record<string, string>).Authorization = `Bearer ${token}`;
        originalRequest.headers = headers;
        return api(originalRequest);
      } catch (refreshError: any) {
        processQueue(refreshError, null);
        clearStoredAuth();
        if (typeof window !== 'undefined') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export const extractErrorMessage = (error: any): string => {
  if (!error) return 'An unknown error occurred.';
  let rawMessage = 'An unexpected error occurred.';

  if (error.response?.data) {
    const data = error.response.data;
    if (typeof data === 'string') {
      rawMessage = data;
    } else if (typeof data === 'object') {
      const messages: string[] = [];
      for (const key in data) {
        if (Object.prototype.hasOwnProperty.call(data, key)) {
          const val = data[key];
          if (Array.isArray(val)) {
            messages.push(`${key}: ${val.join(', ')}`);
          } else if (typeof val === 'string') {
            messages.push(val);
          } else {
            messages.push(`${key}: ${JSON.stringify(val)}`);
          }
        }
      }
      if (messages.length > 0) {
        rawMessage = messages.join(' ');
      }
    }
  } else if (error.message) {
    rawMessage = error.message;
  }

  // Mitigate XSS & HTML injection: strictly escape any HTML tags by replacing characters
  return rawMessage
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')
    .replace(/\//g, '&#x2F;');
};

export const authService = {
  register: async (payload: RegisterPayload): Promise<RegisterResponse> => {
    const response = await api.post<RegisterResponse>('/auth/register/', payload);
    return response.data;
  },
  login: async (payload: LoginPayload): Promise<AuthTokens> => {
    const response = await api.post<TokenResponseShape>('auth/login/', payload);
    return normalizeTokenResponse(response.data);
  },
  refresh: async (refreshToken: string): Promise<AuthTokens> => {
    const response = await api.post<TokenResponseShape>('auth/refresh/', { refresh: refreshToken });
    return normalizeTokenResponse(response.data);
  },
};

export const trackerService = {
  listProducts: () => api.get<TrackedProduct[]>('trackers/products/'),
  createProduct: (payload: Omit<TrackedProduct, 'id' | 'created_at' | 'last_scraped_at' | 'domain_name' | 'price_histories'>) =>
    api.post<TrackedProduct>('trackers/products/', payload),
  updateProduct: (id: number, payload: Partial<TrackedProduct>) => api.put<TrackedProduct>(`trackers/products/${id}/`, payload),
  deleteProduct: (id: number) => api.delete(`trackers/products/${id}/`),
};

export const analyticsService = {
  getSummary: () => api.get<AnalyticsSummary>('analytics/summary/'),
};

export default api;

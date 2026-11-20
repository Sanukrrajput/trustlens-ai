import type {
  AdminDashboard,
  AdminUserCreate,
  CommunityReportCreate,
  AnalysisListItem,
  AnalysisResult,
  ApiErrorShape,
  CheckoutOut,
  CheckoutRequest,
  LoginMode,
  LoginOptions,
  LoginSecurity,
  MonitoringTaskCreate,
  MonitoringTaskOut,
  NotificationOut,
  Paginated,
  PlanOut,
  SigninEvent,
  SigninSummary,
  SubscriptionOut,
  SupportChatClearResult,
  SupportChatMessage,
  SupportChatReply,
  SupportChatRequest,
  SystemConfig,
  TaskStatusOut,
  TokenPair,
  User,
  ReportReviewUpdate,
  UserReportCreate,
  UserReportOut,
} from '../types';

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '/api/v1';

const ACCESS_KEY = 'trustlens.access_token';
const REFRESH_KEY = 'trustlens.refresh_token';
const USER_KEY = 'trustlens.user';
const DEVICE_KEY = 'trustlens.device_id';
const REMEMBERED_KEY = 'trustlens.remembered_signin';
export const UNAUTHORIZED_EVENT = 'trustlens:unauthorized';

export interface RememberedSignin {
  email: string;
  mode?: LoginMode;
  device_id?: string;
  previous_signin?: SigninSummary | null;
  saved_at: string;
}

function newDeviceId(): string {
  const browserCrypto = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;
  if (browserCrypto?.randomUUID) return browserCrypto.randomUUID();
  return `device-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Stable, non-sensitive browser identifier used for remembered sign-ins. */
export function getDeviceId(): string {
  try {
    const existing = localStorage.getItem(DEVICE_KEY);
    if (existing) return existing;
    const created = newDeviceId();
    localStorage.setItem(DEVICE_KEY, created);
    return created;
  } catch {
    return newDeviceId();
  }
}

export function rotateDeviceId(): string {
  const created = newDeviceId();
  try {
    localStorage.setItem(DEVICE_KEY, created);
  } catch {
    /* storage unavailable — the new id is still used for this session */
  }
  return created;
}

export function getRememberedSignin(): RememberedSignin | null {
  try {
    const raw = localStorage.getItem(REMEMBERED_KEY);
    return raw ? (JSON.parse(raw) as RememberedSignin) : null;
  } catch {
    return null;
  }
}

export function saveRememberedSignin(value: RememberedSignin): void {
  try {
    localStorage.setItem(REMEMBERED_KEY, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

export function clearRememberedSignin(): void {
  try {
    localStorage.removeItem(REMEMBERED_KEY);
  } catch {
    /* ignore */
  }
}

export class ApiError extends Error {
  status: number;
  payload?: ApiErrorShape;

  constructor(message: string, status: number, payload?: ApiErrorShape) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_KEY);
  } catch {
    return null;
  }
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function setTokens(tokens: TokenPair): void {
  try {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  } catch {
    /* storage unavailable (private mode) — session-only operation continues */
  }
}

export function setStoredUser(user: User): void {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* ignore */
  }
}

export function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function clearTokens(): void {
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Skip the Authorization header (used for public endpoints). */
  anonymous?: boolean;
}

function buildUrl(path: string, params?: RequestOptions['params']): string {
  const base = API_BASE.replace(/\/$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  const url = `${base}${suffix}`;
  if (!params) return url;
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `${url}?${query}` : url;
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as ApiErrorShape).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first?.msg) return `${first.loc?.join('.') ? `${first.loc.join('.')}: ` : ''}${first.msg}`;
  }
  if (typeof (payload as ApiErrorShape).message === 'string') return (payload as ApiErrorShape).message!;
  return fallback;
}

async function refreshTokens(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const response = await fetch(buildUrl('/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!response.ok) return false;
    const tokens = (await readBody(response)) as TokenPair | undefined;
    if (!tokens?.access_token || !tokens?.refresh_token) return false;
    setTokens(tokens);
    return true;
  } catch {
    return false;
  }
}

/** Core request helper. Refreshes an expired access token once, then retries. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, params, headers = {}, signal, anonymous = false } = options;
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const requestHeaders: Record<string, string> = { ...headers };
  if (!isForm) requestHeaders['Content-Type'] = 'application/json';
  const token = anonymous ? null : getAccessToken();
  if (token) requestHeaders.Authorization = `Bearer ${token}`;

  const send = () =>
    fetch(buildUrl(path, params), {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      signal,
    });

  let response = await send();

  if (response.status === 401 && !anonymous && !path.includes('/auth/')) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      const newToken = getAccessToken();
      if (newToken) requestHeaders.Authorization = `Bearer ${newToken}`;
      response = await send();
    }
    if (response.status === 401) {
      clearTokens();
      if (typeof window !== 'undefined') window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
  }

  const payload = await readBody(response);
  if (!response.ok) {
    throw new ApiError(errorMessage(payload, `Request failed (${response.status})`), response.status, payload as ApiErrorShape);
  }
  return payload as T;
}

export const authApi = {
  register: (data: {
    email: string;
    password: string;
    full_name: string;
    organisation?: string;
    consent_privacy: boolean;
    consent_terms: boolean;
  }) => api<User>('/auth/register', { method: 'POST', body: data, anonymous: true }),
  login: (email: string, password: string, options: LoginOptions = {}) =>
    api<TokenPair>('/auth/login', {
      method: 'POST',
      body: { email, password, ...options },
      anonymous: true,
    }),
  securityConfig: () => api<LoginSecurity>('/auth/security-config', { anonymous: true }),
  signinActivity: (limit = 10) =>
    api<SigninEvent[]>('/auth/signin-activity', { params: { limit } }),
  me: () => api<User>('/auth/me'),
  refresh: (refresh_token: string) =>
    api<TokenPair>('/auth/refresh', { method: 'POST', body: { refresh_token }, anonymous: true }),
  verifyEmail: (token: string) =>
    api<{ message?: string }>('/auth/verify-email', { method: 'POST', body: { token }, anonymous: true }),
  forgotPassword: (email: string) =>
    api<{ message?: string }>('/auth/forgot-password', { method: 'POST', body: { email }, anonymous: true }),
  resetPassword: (token: string, new_password: string) =>
    api<{ message?: string }>('/auth/reset-password', { method: 'POST', body: { token, new_password }, anonymous: true }),
  logout: () => api<{ message?: string }>('/auth/logout', { method: 'POST' }),
};

export const analysisApi = {
  submitJob: (body: Record<string, unknown>) => api<AnalysisResult | TaskStatusOut>('/analysis/job', { method: 'POST', body }),
  submitOffer: (body: Record<string, unknown>) => api<AnalysisResult | TaskStatusOut>('/analysis/offer', { method: 'POST', body }),
  submitMessage: (body: Record<string, unknown>) => api<AnalysisResult | TaskStatusOut>('/analysis/message', { method: 'POST', body }),
  submitUrl: (body: Record<string, unknown>) => api<AnalysisResult | TaskStatusOut>('/analysis/url', { method: 'POST', body }),
  submitDocument: (file: File, consentExternalLookups: boolean) => {
    const form = new FormData();
    form.append('file', file);
    form.append('consent_external_lookups', String(consentExternalLookups));
    return api<AnalysisResult | TaskStatusOut>('/analysis/document', { method: 'POST', body: form });
  },
  get: (id: string) => api<AnalysisResult>(`/analysis/${encodeURIComponent(id)}`),
  list: (params: { page?: number; page_size?: number; analysis_type?: string } = {}) =>
    api<Paginated<AnalysisListItem>>('/analysis', { params: { ...params } }),
};

export const companyApi = {
  verify: (body: {
    company_name: string;
    website_url?: string;
    corporate_id?: string;
    consent_external_lookups?: boolean;
    consent_corporate_registry_lookup?: boolean;
  }) => api<Record<string, unknown>>('/company/verify', { method: 'POST', body }),
  get: (id: string) => api<Record<string, unknown>>(`/company/${encodeURIComponent(id)}`),
};

export const monitoringApi = {
  list: () => api<MonitoringTaskOut[] | Paginated<MonitoringTaskOut>>('/monitoring'),
  create: (body: MonitoringTaskCreate) => api<MonitoringTaskOut>('/monitoring', { method: 'POST', body }),
  remove: (id: string) => api<{ message?: string }>(`/monitoring/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};

export const reportsApi = {
  get: (id: string) => api<Record<string, unknown>>(`/reports/${encodeURIComponent(id)}`),
  pdf: async (id: string): Promise<Blob> => {
    const token = getAccessToken();
    const response = await fetch(buildUrl(`/reports/${encodeURIComponent(id)}/pdf`), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) throw new ApiError('Could not download the PDF report.', response.status);
    return response.blob();
  },
  feedback: (body: UserReportCreate) => api<UserReportOut>('/reports/feedback', { method: 'POST', body }),
  community: (body: CommunityReportCreate) => api<UserReportOut>('/reports/community', { method: 'POST', body }),
};

export const notificationsApi = {
  list: () => api<NotificationOut[] | Paginated<NotificationOut>>('/notifications'),
  markRead: (id: string) => api<NotificationOut>(`/notifications/${encodeURIComponent(id)}/read`, { method: 'PATCH' }),
};

export const billingApi = {
  plans: () => api<PlanOut[]>('/billing/plans'),
  checkout: (body: CheckoutRequest) => api<CheckoutOut>('/billing/checkout', { method: 'POST', body }),
  subscription: () => api<SubscriptionOut>('/billing/subscription'),
};

export const adminApi = {
  dashboard: () => api<AdminDashboard>('/admin/dashboard'),
  models: () => api<unknown>('/admin/models'),
  reports: () => api<unknown>('/admin/reports'),
  reviewReport: (id: string, body: ReportReviewUpdate) =>
    api<UserReportOut>(`/admin/reports/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
  users: () => api<unknown>('/admin/users'),
  createUser: (body: AdminUserCreate) =>
    api<User>('/admin/users', { method: 'POST', body }),
  auditLogs: () => api<unknown>('/admin/audit-logs'),
};

export const supportApi = {
  ask: (body: SupportChatRequest) =>
    api<SupportChatReply>('/support/chat', { method: 'POST', body, anonymous: true }),
  history: (sessionId: string) =>
    api<SupportChatMessage[]>('/support/chat', {
      params: { session_id: sessionId },
      anonymous: true,
    }),
  clear: (sessionId: string) =>
    api<SupportChatClearResult>('/support/chat', {
      method: 'DELETE',
      params: { session_id: sessionId },
      anonymous: true,
    }),
};

export const systemApi = {
  config: () => api<SystemConfig>('/system/config', { anonymous: true }),
  health: () => api<Record<string, unknown>>('/health', { anonymous: true }),
};

export function isTaskStatus(value: unknown): value is TaskStatusOut {
  return !!value && typeof value === 'object' && 'task_id' in value;
}

export function isAnalysisResult(value: unknown): value is AnalysisResult {
  return !!value && typeof value === 'object' && 'risk' in value && 'indicators' in value;
}

/** Accepts either an immediate result or an async task and resolves to a usable analysis id. */
export async function resolveAnalysis(
  initial: AnalysisResult | TaskStatusOut,
  maxAttempts = 30,
  waitMs = 1500,
): Promise<{ id: string; result?: AnalysisResult; status: string }> {
  if (isAnalysisResult(initial)) {
    return { id: initial.id, result: initial, status: initial.status };
  }
  let task: TaskStatusOut = initial;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (task.result && isAnalysisResult(task.result)) {
      return { id: task.result.id, result: task.result, status: 'completed' };
    }
    if (task.status === 'completed' || task.status === 'failed') {
      const candidate = (task.result ?? {}) as Record<string, unknown>;
      const id = String(candidate.id ?? task.task_id);
      if (task.status === 'failed') throw new ApiError(task.error || 'Analysis failed.', 500);
      const result = await analysisApi.get(id).catch(() => undefined);
      return { id, result, status: task.status };
    }
    await new Promise((resolve) => setTimeout(resolve, waitMs));
    const next = await api<AnalysisResult | TaskStatusOut>(`/analysis/${encodeURIComponent(task.task_id)}`);
    if (isAnalysisResult(next)) {
      return { id: next.id, result: next, status: next.status };
    }
    task = next;
  }
  throw new ApiError('Analysis timed out. Check your investigations shortly.', 504);
}

export function unwrapList<T>(value: T[] | Paginated<T> | undefined): T[] {
  if (!value) return [];
  return Array.isArray(value) ? value : value.items ?? [];
}

const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');
const API_KEY = import.meta.env.VITE_API_KEY || '';

export async function api(path, { method = 'GET', body, params } = {}) {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
  });
  const response = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail || payload);
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const endpoints = {
  summary: '/core/overview/summary',
  eventsOverTime: '/core/overview/events-over-time',
  events: '/core/events',
  detections: '/core/detections',
  incidents: '/core/incidents',
  investigation: (id) => `/core/incidents/${encodeURIComponent(id)}/investigation`,
  indicators: '/intel/indicators',
  enrich: '/intel/indicators/enrich',
  assets: '/intel/assets',
  models: '/intel/models',
  sources: '/intel/sources',
  jobs: '/intel/jobs',
  settings: '/intel/settings',
  health: '/intel/system/health',
  status: '/status',
  notifications: '/admin/notifications',
  audit: '/admin/audit-logs',
  actions: '/admin/response-actions',
  runJob: (name) => `/core/run/${name}`,
  collect: (name) => `/intel/sources/${encodeURIComponent(name)}/collect`,
  train: '/intel/models/train',
};

import type { EvidenceStatus } from '../types';

export function cx(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ');
}

export function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relativeTime(value?: string | null): string {
  if (!value) return '—';
  const diff = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diff)) return '—';
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function formatMoney(paise: number, currency = 'INR'): string {
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(paise / 100);
  } catch {
    return `${currency} ${(paise / 100).toFixed(0)}`;
  }
}

export function pct(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

export function scoreColor(score: number): string {
  if (score >= 75) return '#ef4444';
  if (score >= 50) return '#f59e0b';
  if (score >= 25) return '#06b6d4';
  return '#10b981';
}

export function riskTone(category?: string | null): 'danger' | 'warn' | 'brand' | 'safe' {
  const value = (category ?? '').toLowerCase();
  if (/critical|high|fraud|malicious|danger/.test(value)) return 'danger';
  if (/medium|moderate|suspicious|caution|elevated/.test(value)) return 'warn';
  if (/low|safe|clear|trusted/.test(value)) return 'safe';
  return 'brand';
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function initials(name: string): string {
  return name
    .split(/[\s@]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

export function truncate(value: string, length = 120): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

export function parseListInput(value: string): string[] {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const EVIDENCE_GROUPS: Array<{ status: EvidenceStatus; label: string; description: string; dot: string }> = [
  { status: 'confirmed_malicious', label: 'Confirmed malicious', description: 'Directly verified harmful signals', dot: '#ef4444' },
  { status: 'verified_inconsistency', label: 'Verified inconsistency', description: 'Contradicted by authoritative sources', dot: '#f97316' },
  { status: 'suspicious', label: 'Suspicious', description: 'Corroborating but not conclusive signals', dot: '#f59e0b' },
  { status: 'unverified', label: 'Unverified', description: 'Claims that could not be independently confirmed', dot: '#06b6d4' },
  { status: 'supportive', label: 'Supportive', description: 'Signals consistent with legitimate activity', dot: '#10b981' },
  { status: 'missing', label: 'Missing evidence', description: 'Information required for a conclusive result', dot: '#94a3b8' },
  { status: 'technical_limitation', label: 'Technical limitation', description: 'Checks unavailable during this analysis', dot: '#64748b' },
];

export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return 'Something went wrong. Please try again.';
}

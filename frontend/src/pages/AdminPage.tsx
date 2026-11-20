import { useState, type ReactNode } from 'react';
import { Activity, AlertTriangle, Cpu, FileText, ScrollText, Server, ShieldCheck, Users } from 'lucide-react';
import { CreateAccountForm } from '../components/CreateAccountForm';
import { DonutChart, RiskDistributionChart, ScanTrendChart } from '../components/Charts';
import { DataTable, type Column } from '../components/DataTable';
import { Badge, Card, EmptyState, ErrorState, SectionHeading, SkeletonBlock, Spinner, StatTile } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { useApi } from '../hooks/useApi';
import { adminApi, systemApi } from '../lib/api';
import { errorText, formatDateTime, titleCase } from '../lib/utils';
import type { AdminDashboard, ModerationState, PlanOut } from '../types';

type Row = Record<string, unknown>;

async function settled<T>(promise: Promise<T>): Promise<{ data?: T; error?: string }> {
  try {
    return { data: await promise };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Request failed' };
  }
}

function extractList(value: unknown): Row[] {
  if (Array.isArray(value)) return value as Row[];
  if (value && typeof value === 'object') {
    for (const key of ['items', 'users', 'reports', 'logs', 'audit_logs', 'models', 'data', 'results']) {
      const candidate = (value as Record<string, unknown>)[key];
      if (Array.isArray(candidate)) return candidate as Row[];
    }
  }
  return [];
}

function cell(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') return <span className="text-muted">—</span>;
  if (typeof value === 'boolean') return <Badge tone={value ? 'safe' : 'warn'}>{value ? 'Yes' : 'No'}</Badge>;
  if (typeof value === 'object') return <code className="text-[11px]">{JSON.stringify(value)}</code>;
  const text = String(value);
  if (/^(active|completed|success|verified|healthy|ok)$/i.test(text)) return <Badge tone="safe" dot>{text}</Badge>;
  if (/^(failed|critical|high|error|down)$/i.test(text)) return <Badge tone="danger" dot>{text}</Badge>;
  if (/^(pending|warning|degraded|medium)$/i.test(text)) return <Badge tone="warn" dot>{text}</Badge>;
  return text;
}

function buildColumns(rows: Row[]): Array<Column<Row>> {
  const keys = [...new Set(rows.slice(0, 8).flatMap((row) => Object.keys(row)))].slice(0, 6);
  if (!keys.length) return [{ key: 'empty', header: 'Record', render: () => '—' }];
  return keys.map((key) => ({
    key,
    header: titleCase(key),
    render: (row) => <span className="max-w-xs truncate">{cell(row[key])}</span>,
  }));
}

function AdminTable({ value, emptyText }: { value: unknown; emptyText: string }) {
  const rows = extractList(value);
  if (!rows.length) return <EmptyState title={emptyText} description="No records were returned by this endpoint." />;
  return <DataTable columns={buildColumns(rows)} rows={rows} rowKey={(row) => String(row.id ?? row.task_id ?? Object.values(row)[0] ?? JSON.stringify(row).slice(0, 48))} compact />;
}

const MODERATION_STATES: ModerationState[] = ['pending', 'verified', 'corroborated', 'false_report', 'dismissed'];

interface ModerationDraft {
  state: ModerationState;
  notes: string;
  reason: string;
  busy: boolean;
  error: string;
}

function defaultDraft(row: Row): ModerationDraft {
  const stored = String(row.moderation_state || 'pending') as ModerationState;
  return {
    state: MODERATION_STATES.includes(stored) ? stored : 'pending',
    notes: '',
    reason: '',
    busy: false,
    error: '',
  };
}

function ReportModerationTable({ rows, onReviewed }: { rows: Row[]; onReviewed: () => void }) {
  const { notify } = useToast();
  const [drafts, setDrafts] = useState<Record<string, ModerationDraft>>({});

  if (!rows.length) return <EmptyState title="No user reports" description="No reports have been submitted yet." />;

  const draftFor = (row: Row): ModerationDraft => drafts[String(row.id)] ?? defaultDraft(row);
  const updateDraft = (row: Row, patch: Partial<ModerationDraft>) => {
    const id = String(row.id);
    setDrafts((current) => ({ ...current, [id]: { ...draftFor(row), ...patch } }));
  };

  const review = async (row: Row) => {
    const id = String(row.id);
    const draft = draftFor(row);
    setDrafts((current) => ({ ...current, [id]: { ...draft, busy: true, error: '' } }));
    try {
      const updated = await adminApi.reviewReport(id, {
        moderation_state: draft.state,
        review_notes: draft.notes.trim() || undefined,
        false_report_reason: draft.state === 'false_report' ? draft.reason.trim() || undefined : undefined,
      });
      notify(`Report ${updated.id.slice(0, 8)} set to ${updated.moderation_state}.`, 'success');
      setDrafts((current) => ({ ...current, [id]: defaultDraft({ ...row, moderation_state: updated.moderation_state }) }));
      onReviewed();
    } catch (error) {
      const message = errorText(error);
      setDrafts((current) => ({ ...current, [id]: { ...draft, busy: false, error: message } }));
      notify(message, 'error');
    }
  };

  const columns: Array<Column<Row>> = [
    { key: 'id', header: 'Report', render: (row) => <code className="text-[11px]">{String(row.id).slice(0, 12)}…</code> },
    {
      key: 'category',
      header: 'Type',
      render: (row) => (
        <Badge tone={row.category === 'community' ? 'warn' : 'brand'}>
          {String(row.category || 'unknown')}
        </Badge>
      ),
    },
    { key: 'report_type', header: 'Claim', render: (row) => <span className="capitalize">{titleCase(String(row.report_type || ''))}</span> },
    {
      key: 'entity_key',
      header: 'Entity',
      render: (row) => <code className="text-[11px]">{row.entity_key ? `${String(row.entity_key).slice(0, 16)}…` : '—'}</code>,
    },
    {
      key: 'moderation_state',
      header: 'State',
      render: (row) => cell(row.moderation_state),
    },
    {
      key: 'reputation',
      header: 'Rep.',
      render: (row) => {
        const reputation = (row.reporter_reputation || {}) as Record<string, unknown>;
        return <span className="font-mono text-xs">{reputation.score === undefined ? '—' : String(reputation.score)}</span>;
      },
    },
    {
      key: 'details',
      header: 'Details',
      render: (row) => <span className="block max-w-[260px] truncate" title={String(row.details || '')}>{String(row.details || '')}</span>,
    },
    {
      key: 'actions',
      header: 'Moderate',
      render: (row) => {
        const id = String(row.id);
        const draft = draftFor(row);
        return (
          <div className="min-w-[290px] space-y-2">
            <div className="flex gap-2">
              <select
                aria-label={`Moderation state for ${id}`}
                className="input h-9 py-1 text-xs"
                value={draft.state}
                onChange={(event) => updateDraft(row, { state: event.target.value as ModerationState })}
              >
                {MODERATION_STATES.map((state) => <option key={state} value={state}>{titleCase(state)}</option>)}
              </select>
              <button
                type="button"
                aria-label={`Apply moderation for ${id}`}
                className="btn-primary h-9 px-3 py-1 text-xs"
                disabled={draft.busy}
                onClick={() => void review(row)}
              >
                {draft.busy ? <Spinner label="" className="min-h-0 p-0" /> : <><ShieldCheck className="h-3.5 w-3.5" /> Apply</>}
              </button>
            </div>
            <input
              aria-label={`Review notes for ${id}`}
              className="input h-9 py-1 text-xs"
              placeholder="Review notes"
              value={draft.notes}
              onChange={(event) => updateDraft(row, { notes: event.target.value })}
            />
            {draft.state === 'false_report' && (
              <input
                aria-label={`False report reason for ${id}`}
                className="input h-9 py-1 text-xs"
                placeholder="Why is this false?"
                value={draft.reason}
                onChange={(event) => updateDraft(row, { reason: event.target.value })}
              />
            )}
            {draft.error && <p className="text-xs text-danger">{draft.error}</p>}
          </div>
        );
      },
    },
  ];
  return <DataTable columns={columns} rows={rows} rowKey={(row) => String(row.id)} compact />;
}

export function AdminPage() {
  const { data, loading, error, refetch } = useApi(async () => {
    const [dashboard, models, reports, users, auditLogs] = await Promise.all([
      settled(adminApi.dashboard()),
      settled(adminApi.models()),
      settled(adminApi.reports()),
      settled(adminApi.users()),
      settled(adminApi.auditLogs()),
    ]);
    return { dashboard, models, reports, users, auditLogs };
  }, []);
  const health = useApi(() => systemApi.health(), []);
  const config = useApi(() => systemApi.config(), []);

  if (loading) return <div className="space-y-6"><SkeletonBlock className="h-10 w-72" /><SkeletonBlock className="h-40" /><SkeletonBlock className="h-80" /></div>;
  if (error) return <ErrorState message={error} onRetry={() => void refetch()} />;
  if (!data) return null;

  const dashboard = (data.dashboard.data ?? {}) as AdminDashboard;
  const errors = [data.dashboard.error, data.models.error, data.reports.error, data.users.error, data.auditLogs.error].filter(Boolean);
  const numericStats = Object.entries(dashboard)
    .filter(([, value]) => typeof value === 'number')
    .slice(0, 4) as Array<[string, number]>;
  const typeData = Array.isArray(dashboard.scans_by_type) ? dashboard.scans_by_type : [];
  const trendData = Array.isArray(dashboard.daily_scans) ? dashboard.daily_scans : [];
  const riskData = Array.isArray(dashboard.risk_distribution) ? dashboard.risk_distribution : [];
  const plans = Array.isArray(config.data?.plans) ? (config.data.plans as unknown as PlanOut[]) : [];
  const healthRows: Row[] = health.data
    ? Object.entries(health.data).map(([key, value]) => ({ component: key, status: value }))
    : [];

  return (
    <div>
      <SectionHeading
        eyebrow="Administration"
        title="Admin console"
        description="Platform-wide monitoring. Read-only views reflect the current API contract."
      />

      {!!errors.length && (
        <div className="mb-6 rounded-xl border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
          Some admin endpoints could not be loaded: {errors.join(' · ')}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {numericStats.length ? numericStats.map(([key, value]) => (
          <StatTile key={key} label={titleCase(key)} value={value.toLocaleString()} icon={<Activity className="h-5 w-5" />} />
        )) : [
          <StatTile key="users" label="Total users" value="—" icon={<Users className="h-5 w-5" />} />,
          <StatTile key="scans" label="Total analyses" value="—" icon={<Activity className="h-5 w-5" />} />,
          <StatTile key="risk" label="High-risk detections" value="—" icon={<AlertTriangle className="h-5 w-5" />} />,
          <StatTile key="api" label="API requests" value="—" icon={<Server className="h-5 w-5" />} />,
        ]}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Scans by type"><DonutChart data={typeData} /></Card>
        <Card title="Risk distribution" className="lg:col-span-2"><RiskDistributionChart data={riskData} /></Card>
      </div>

      <Card className="mt-6" title="API usage over time"><ScanTrendChart data={trendData} /></Card>

      <Card
        className="mt-6"
        title="Create account"
        subtitle="Admin-only account provisioning with role limits and audit logging"
      >
        <CreateAccountForm onCreated={() => void refetch()} />
      </Card>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card title="Model performance" subtitle={data.models.error ?? 'Registered models and reported metrics'}>
          <AdminTable value={data.models.data} emptyText="No model metrics" />
        </Card>
        <Card
          className="xl:col-span-2"
          title="Community reports and corrections"
          subtitle={data.reports.error ?? 'Moderator review states are audited; false reports lower reporter reputation'}
        >
          <ReportModerationTable
            rows={extractList(data.reports.data)}
            onReviewed={() => void refetch()}
          />
        </Card>
        <Card title="Users" subtitle={data.users.error ?? 'Account directory'}>
          <AdminTable value={data.users.data} emptyText="No users returned" />
        </Card>
        <Card title="Audit logs" subtitle={data.auditLogs.error ?? 'Recent administrative and security events'}>
          <AdminTable value={data.auditLogs.data} emptyText="No audit events" />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card title="System health" subtitle={<span className="flex items-center gap-1.5"><Server className="h-3.5 w-3.5" /> GET /health</span>}>
          {health.loading ? <Spinner /> : health.error ? <ErrorState message={health.error} onRetry={() => void health.refetch()} /> : (
            <DataTable
              columns={[
                { key: 'component', header: 'Component', render: (row) => <span className="capitalize">{String(row.component)}</span> },
                { key: 'status', header: 'Status', render: (row) => <span className="font-mono text-xs">{cell(row.status)}</span> },
              ]}
              rows={healthRows}
              rowKey={(row) => String(row.component)}
              compact
            />
          )}
        </Card>

        <Card title="Plan configuration" subtitle="Read-only — no plan update endpoint in the current contract">
          {config.loading ? <Spinner /> : config.error ? <ErrorState message={config.error} onRetry={() => void config.refetch()} /> : plans.length ? (
            <DataTable
              columns={[
                { key: 'plan', header: 'Plan', render: (row) => <span className="font-semibold">{String(row.name)} <span className="text-xs text-muted">({String(row.code)})</span></span> },
                { key: 'price', header: 'Monthly', render: (row) => <span className="font-mono text-xs">{String(row.price_monthly_paise)} {String(row.currency)}</span> },
                { key: 'limit', header: 'Scan limit', render: (row) => String(row.scan_limit) },
                { key: 'status', header: 'Status', render: (row) => <Badge tone={row.active ? 'safe' : 'warn'}>{row.active ? 'Active' : 'Inactive'}</Badge> },
              ]}
              rows={plans as unknown as Row[]}
              rowKey={(row) => String(row.code)}
              compact
            />
          ) : <EmptyState icon={<FileText className="h-5 w-5" />} title="No plan configuration returned" />}
        </Card>
      </div>

      <p className="mt-6 flex items-center gap-2 text-xs text-muted"><Cpu className="h-4 w-4" /> Admin data fetched at {formatDateTime(new Date().toISOString())}. Values are not cached.</p>
      <p className="mt-2 flex items-center gap-2 text-xs text-muted"><ScrollText className="h-4 w-4" /> Audit history is filtered and ordered by the backend.</p>
    </div>
  );
}

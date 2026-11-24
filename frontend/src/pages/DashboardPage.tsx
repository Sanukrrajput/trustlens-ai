import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Bell,
  Building2,
  CheckCircle2,
  FileSearch,
  Radar,
  ShieldAlert,
} from 'lucide-react';
import { RiskDistributionChart, ScanTrendChart } from '../components/Charts';
import { DataTable, type Column } from '../components/DataTable';
import { Badge, Card, EmptyState, ErrorState, ProgressBar, SectionHeading, Spinner, StatTile } from '../components/ui';
import { useApi } from '../hooks/useApi';
import {
  analysisApi,
  billingApi,
  monitoringApi,
  notificationsApi,
  systemApi,
  unwrapList,
} from '../lib/api';
import { formatDateTime, relativeTime, riskTone, titleCase } from '../lib/utils';
import type { AnalysisListItem, NotificationOut } from '../types';

async function settled<T>(promise: Promise<T>): Promise<{ data?: T; error?: string }> {
  try {
    return { data: await promise };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Request failed' };
  }
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { data, loading, error, refetch } = useApi(async () => {
    const [analyses, notifications, monitors, subscription] = await Promise.all([
      settled(analysisApi.list({ page: 1, page_size: 100 })),
      settled(notificationsApi.list()),
      settled(monitoringApi.list()),
      settled(billingApi.subscription()),
    ]);
    return { analyses, notifications, monitors, subscription };
  }, []);
  const { data: health } = useApi(() => systemApi.health(), []);

  if (loading) return <Spinner label="Loading your dashboard…" className="min-h-[60vh]" />;
  if (error) return <ErrorState message={error} onRetry={() => void refetch()} />;
  if (!data) return null;

  const analyses = data.analyses.data?.items ?? [];
  const totalScans = data.analyses.data?.total ?? analyses.length;
  const alerts = unwrapList(data.notifications.data as NotificationOut[] | undefined);
  const monitors = unwrapList(data.monitors.data);
  const subscription = data.subscription.data;

  const highRisk = analyses.filter((item) => (item.risk_score ?? 0) >= 70 || /high|critical|fraud/i.test(item.risk_category ?? '')).length;
  const inconclusive = analyses.filter((item) => /inconclusive/i.test(item.risk_category ?? '')).length;
  const medium = analyses.filter((item) => (item.risk_score ?? 0) >= 40 && (item.risk_score ?? 0) < 70 && !/inconclusive/i.test(item.risk_category ?? '')).length;
  const low = Math.max(0, analyses.length - highRisk - medium - inconclusive);
  const riskData = [
    { name: 'High', value: highRisk },
    { name: 'Medium', value: medium },
    { name: 'Low', value: low },
    { name: 'Inconclusive', value: inconclusive },
  ];

  const trendMap = new Map<string, number>();
  analyses.forEach((item) => {
    const key = new Date(item.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    trendMap.set(key, (trendMap.get(key) ?? 0) + 1);
  });
  const trend = [...trendMap.entries()].slice(-7).map(([date, count]) => ({ date, count }));
  const companies = [...new Set(analyses.map((item) => item.company_name).filter((name): name is string => !!name))].slice(0, 5);
  const unread = alerts.filter((item) => !item.read).length;

  const columns: Array<Column<AnalysisListItem>> = [
    {
      key: 'input',
      header: 'Investigation',
      render: (row) => (
        <div className="max-w-md">
          <p className="truncate font-semibold">{row.company_name ?? titleCase(row.analysis_type)}</p>
          <p className="truncate text-xs text-muted">{row.input_preview}</p>
        </div>
      ),
    },
    { key: 'type', header: 'Type', render: (row) => <span className="capitalize">{row.analysis_type}</span> },
    {
      key: 'risk',
      header: 'Risk',
      render: (row) =>
        row.risk_score !== null && row.risk_score !== undefined ? (
          <Badge tone={riskTone(row.risk_category)}>{row.risk_score} · {row.risk_category ? titleCase(row.risk_category) : 'Scored'}</Badge>
        ) : (
          <Badge tone="neutral">Not scored</Badge>
        ),
    },
    { key: 'date', header: 'Created', render: (row) => <span className="text-muted">{relativeTime(row.created_at)}</span> },
    { key: 'go', header: '', render: () => <ArrowUpRight className="h-4 w-4 text-muted" />, headerClassName: 'sr-only' },
  ];

  const usage = subscription ? Math.round((subscription.scans_used / Math.max(1, subscription.scan_limit)) * 100) : null;

  return (
    <div>
      <SectionHeading
        eyebrow="Workspace overview"
        title="Your risk intelligence at a glance"
        description="All figures come from your live investigations, notifications and subscription."
        action={
          <Link to="/app/scan" className="btn-primary">
            <FileSearch className="h-4 w-4" /> New investigation
          </Link>
        }
      />

      {(data.analyses.error || data.notifications.error || data.monitors.error || data.subscription.error) && (
        <div className="mb-6 rounded-xl border border-warn/30 bg-warn/10 px-4 py-3 text-sm text-warn">
          Some sections could not be loaded: {[data.analyses.error, data.notifications.error, data.monitors.error, data.subscription.error].filter(Boolean).join(' · ')}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total scans" value={totalScans} hint={data.analyses.error ? 'Analysis service unavailable' : 'Across all analysis types'} icon={<FileSearch className="h-5 w-5" />} />
        <StatTile label="High-risk detections" value={highRisk} hint={highRisk ? 'Review these investigations first' : 'No high-risk findings in loaded scans'} tone="danger" icon={<ShieldAlert className="h-5 w-5" />} />
        <StatTile label="Unread alerts" value={unread} hint={`${monitors.length} active monitoring task${monitors.length === 1 ? '' : 's'}`} tone="warn" icon={<Bell className="h-5 w-5" />} />
        <StatTile label="Companies tracked" value={companies.length} hint="Distinct companies seen in your investigations" icon={<Building2 className="h-5 w-5" />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Risk distribution" subtitle="Based on your most recent 100 investigations" className="lg:col-span-1">
          <RiskDistributionChart data={riskData} />
        </Card>
        <Card title="Investigation activity" subtitle="Scans grouped by creation date" className="lg:col-span-2">
          <ScanTrendChart data={trend} />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Recent investigations" action={<Link to="/app/scan" className="link text-xs">Start new scan →</Link>}>
          <DataTable
            columns={columns}
            rows={analyses.slice(0, 6)}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/app/reports/${row.id}`)}
            emptyTitle="No investigations yet"
            emptyDescription="Run your first scan to see results here."
            compact
          />
        </Card>

        <div className="space-y-6">
          <Card title="Recent alerts" action={<Link to="/app/settings" className="link text-xs">All notifications →</Link>}>
            {alerts.length ? (
              <ul className="divide-y divide-line">
                {alerts.slice(0, 5).map((alert) => (
                  <li key={alert.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                    <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${alert.read ? 'bg-line' : 'bg-brand-500'}`} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{alert.title}</p>
                      <p className="line-clamp-2 text-xs text-muted">{alert.body}</p>
                      <p className="mt-1 text-[11px] text-muted">{relativeTime(alert.created_at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={<Bell className="h-5 w-5" />} title="No alerts yet" description="Monitoring alerts will appear here." />
            )}
          </Card>

          <Card title="Plan usage">
            {subscription ? (
              <>
                <div className="flex items-end justify-between">
                  <div>
                    <p className="text-2xl font-bold tabular-nums">{subscription.scans_used}<span className="text-sm font-medium text-muted"> / {subscription.scan_limit || '∞'}</span></p>
                    <p className="mt-1 text-xs text-muted">Scans used this period · {subscription.plan_code}</p>
                  </div>
                  <Badge tone={subscription.status === 'active' ? 'safe' : 'warn'} dot>{subscription.status}</Badge>
                </div>
                <ProgressBar value={usage ?? 0} tone={(usage ?? 0) > 85 ? 'danger' : 'brand'} className="mt-4" />
                <Link to="/app/billing" className="link mt-4 inline-flex items-center gap-1 text-xs">Manage plan <ArrowUpRight className="h-3 w-3" /></Link>
              </>
            ) : (
              <EmptyState title="No active subscription" description="You may be on a free tier. View available plans to expand your limits." action={<Link to="/app/billing" className="btn-secondary">View plans</Link>} />
            )}
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Companies in your investigations">
          {companies.length ? (
            <div className="flex flex-wrap gap-2">
              {companies.map((company) => <span key={company} className="chip"><Building2 className="h-3.5 w-3.5" /> {company}</span>)}
            </div>
          ) : (
            <EmptyState title="No companies recorded" description="Company names extracted from scans will be listed here." />
          )}
        </Card>
        <Card title="Monitoring status">
          <div className="flex items-center gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500"><Radar className="h-5 w-5" /></div>
            <div>
              <p className="text-2xl font-bold tabular-nums">{monitors.length}</p>
              <p className="text-xs text-muted">Tasks configured</p>
            </div>
          </div>
          <Link to="/app/monitoring" className="link mt-4 inline-block text-xs">Manage monitors →</Link>
        </Card>
        <Card title="System health">
          {health ? (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted">API</span>
                <Badge tone="safe" dot><CheckCircle2 className="h-3 w-3" /> Operational</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted">Environment</span>
                <span className="font-medium">{String(health.environment ?? 'production')}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted">Version</span>
                <span className="font-mono text-xs">{String(health.version ?? '—')}</span>
              </div>
            </div>
          ) : (
            <p className="flex items-center gap-2 text-sm text-muted"><Activity className="h-4 w-4" /> Health endpoint unavailable.</p>
          )}
        </Card>
      </div>

      {data.analyses.error && !analyses.length && (
        <div className="mt-6"><ErrorState message={data.analyses.error} onRetry={() => void refetch()} /></div>
      )}
      {!data.analyses.error && !analyses.length && (
        <Card className="mt-6">
          <EmptyState
            icon={<AlertTriangle className="h-5 w-5" />}
            title="Start your first investigation"
            description="Paste an offer, message, URL or screenshot. You will receive evidence, confidence, missing information and next steps — not a blind verdict."
            action={<Link to="/app/scan" className="btn-primary">Check an offer</Link>}
          />
        </Card>
      )}
      <p className="mt-6 text-center text-xs text-muted">Dashboard last refreshed {formatDateTime(new Date().toISOString())}</p>
    </div>
  );
}

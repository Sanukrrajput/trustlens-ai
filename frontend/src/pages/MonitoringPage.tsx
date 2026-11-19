import { useState, type FormEvent } from 'react';
import { Bell, CalendarClock, Loader2, Plus, Radar, Trash2 } from 'lucide-react';
import { DataTable, type Column } from '../components/DataTable';
import { Badge, Card, ErrorState, Field, SectionHeading, Spinner } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { useApi } from '../hooks/useApi';
import { monitoringApi, unwrapList } from '../lib/api';
import { errorText, formatDateTime, parseListInput, relativeTime } from '../lib/utils';
import { validateMonitoring } from '../lib/validation';
import type { MonitoringTaskOut } from '../types';

export function MonitoringPage() {
  const { notify } = useToast();
  const { data, loading, error, refetch, setData } = useApi(() => monitoringApi.list().then(unwrapList), []);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [form, setForm] = useState({
    name: '',
    company_names: '',
    job_titles: '',
    source_urls: '',
    keywords: '',
    notify_email: true,
    notify_in_app: true,
  });

  const tasks = data ?? [];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const payload = {
      name: form.name.trim(),
      company_names: parseListInput(form.company_names),
      job_titles: parseListInput(form.job_titles),
      source_urls: parseListInput(form.source_urls),
      keywords: parseListInput(form.keywords),
    };
    const found = validateMonitoring(payload);
    setErrors(found);
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      const created = await monitoringApi.create({ ...payload, enabled: true, notify_email: form.notify_email, notify_in_app: form.notify_in_app });
      setData([created, ...tasks]);
      setShowForm(false);
      setForm({ name: '', company_names: '', job_titles: '', source_urls: '', keywords: '', notify_email: true, notify_in_app: true });
      notify('Monitoring task created.', 'success');
    } catch (err) {
      notify(errorText(err), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (task: MonitoringTaskOut) => {
    if (!window.confirm(`Delete monitoring task “${task.name}”?`)) return;
    try {
      await monitoringApi.remove(task.id);
      setData(tasks.filter((item) => item.id !== task.id));
      notify('Monitoring task deleted.', 'success');
    } catch (err) {
      notify(errorText(err), 'error');
    }
  };

  const columns: Array<Column<MonitoringTaskOut>> = [
    {
      key: 'name',
      header: 'Task',
      render: (row) => (
        <div>
          <p className="font-semibold">{row.name}</p>
          <p className="mt-0.5 text-xs text-muted">
            {[...row.company_names, ...row.job_titles, ...row.keywords].slice(0, 3).join(' · ') || 'No targets listed'}
          </p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <div className="flex flex-wrap gap-1.5">
          <Badge tone={row.enabled ? 'safe' : 'neutral'} dot>{row.enabled ? 'Enabled' : 'Paused'}</Badge>
          {row.last_status && <Badge tone="neutral">{row.last_status}</Badge>}
        </div>
      ),
    },
    {
      key: 'prefs',
      header: 'Notifications',
      render: (row) => (
        <div className="flex flex-wrap gap-1.5 text-xs text-muted">
          {row.notify_email && <span className="chip">Email</span>}
          {row.notify_in_app && <span className="chip">In-app</span>}
          {!row.notify_email && !row.notify_in_app && <span>All off</span>}
        </div>
      ),
    },
    { key: 'last', header: 'Last run', render: (row) => <span className="text-muted">{row.last_run_at ? relativeTime(row.last_run_at) : 'Never'}</span> },
    {
      key: 'actions',
      header: '',
      headerClassName: 'sr-only',
      render: (row) => (
        <button className="rounded-lg p-2 text-danger hover:bg-danger/10" aria-label={`Delete ${row.name}`} onClick={(event) => { event.stopPropagation(); void remove(row); }}>
          <Trash2 className="h-4 w-4" />
        </button>
      ),
    },
  ];

  return (
    <div>
      <SectionHeading
        eyebrow="Continuous vigilance"
        title="Job monitoring"
        description="Track companies, roles, keywords and source URLs. Notifications appear in your workspace and optionally by email."
        action={
          <button className="btn-primary" onClick={() => setShowForm((value) => !value)}>
            {showForm ? 'Cancel' : <><Plus className="h-4 w-4" /> New monitor</>}
          </button>
        }
      />

      {showForm && (
        <Card className="mb-6" title="Create monitoring task">
          <form onSubmit={submit} noValidate className="space-y-4">
            <Field label="Task name" htmlFor="monitor-name" error={errors.name} required>
              <input id="monitor-name" className="input" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="e.g. Remote finance roles" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Company names" hint="Comma or newline separated">
                <textarea id="monitor-companies" className="input min-h-[80px]" value={form.company_names} onChange={(event) => setForm((current) => ({ ...current, company_names: event.target.value }))} placeholder="Acme Corp, Example Ltd" />
              </Field>
              <Field label="Job titles" hint="Comma or newline separated">
                <textarea id="monitor-titles" className="input min-h-[80px]" value={form.job_titles} onChange={(event) => setForm((current) => ({ ...current, job_titles: event.target.value }))} placeholder="Remote Accountant" />
              </Field>
              <Field label="Keywords">
                <input id="monitor-keywords" className="input" value={form.keywords} onChange={(event) => setForm((current) => ({ ...current, keywords: event.target.value }))} placeholder="gift card, urgent, no interview" />
              </Field>
              <Field label="Source URLs" error={errors.source_urls}>
                <input id="monitor-urls" className="input" value={form.source_urls} onChange={(event) => setForm((current) => ({ ...current, source_urls: event.target.value }))} placeholder="https://careers.example.com" />
              </Field>
            </div>
            {errors.targets && <p role="alert" className="text-sm text-danger">{errors.targets}</p>}
            <div className="flex flex-wrap gap-6 rounded-xl border border-line bg-elevated/50 p-4">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.notify_email} onChange={(event) => setForm((current) => ({ ...current, notify_email: event.target.checked }))} /> Email notifications</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-brand-600" checked={form.notify_in_app} onChange={(event) => setForm((current) => ({ ...current, notify_in_app: event.target.checked }))} /> In-app notifications</label>
            </div>
            <button className="btn-primary" type="submit" disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Radar className="h-4 w-4" /> Create monitor</>}
            </button>
          </form>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_19rem]">
        <Card title="Your monitors" subtitle={`${tasks.length} configured task${tasks.length === 1 ? '' : 's'}`}>
          {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={() => void refetch()} /> : (
            <DataTable
              columns={columns}
              rows={tasks}
              rowKey={(row) => row.id}
              emptyTitle="No monitoring tasks"
              emptyDescription="Create a monitor to track companies, roles and keywords over time."
              compact
            />
          )}
        </Card>

        <div className="space-y-5">
          <Card title="Notification preferences">
            <p className="text-sm leading-relaxed text-muted">
              Per-task email and in-app delivery are configured when you create a monitor. Global notification preferences and quiet hours are managed in Settings.
            </p>
            <p className="mt-4 flex items-center gap-2 text-xs text-muted"><Bell className="h-4 w-4 text-brand-500" /> You can change preferences at any time.</p>
          </Card>
          <Card title="How monitoring works">
            <ul className="space-y-3 text-sm text-muted">
              <li className="flex gap-2"><CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> Tasks are evaluated on the backend schedule.</li>
              <li className="flex gap-2"><Radar className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> New matches create notifications and can be linked to an analysis.</li>
              <li className="flex gap-2"><Bell className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> Delete a task at any time to stop collection.</li>
            </ul>
            <p className="mt-4 text-[11px] text-muted">Last sync shown in table: {formatDateTime(new Date().toISOString())}</p>
          </Card>
        </div>
      </div>
    </div>
  );
}

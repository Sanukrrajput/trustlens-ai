import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Building2, CheckCircle2, ExternalLink, Loader2, Search, ShieldCheck } from 'lucide-react';
import { DataTable, type Column } from '../components/DataTable';
import { Badge, Card, EmptyState, ErrorState, Field, SectionHeading, Spinner } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { analysisApi, companyApi } from '../lib/api';
import { errorText, formatDateTime, relativeTime, riskTone, titleCase } from '../lib/utils';
import { validateCompany } from '../lib/validation';
import type { AnalysisListItem } from '../types';

export function CompanyIntelligencePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ company_name: '', website_url: '', corporate_id: '' });
  const [external, setExternal] = useState(false);
  const [registry, setRegistry] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const history = useApi(() => analysisApi.list({ page: 1, page_size: 100 }), []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateCompany(form);
    setErrors(found);
    setServerError('');
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      const response = await companyApi.verify({
        company_name: form.company_name.trim(),
        website_url: form.website_url.trim() || undefined,
        corporate_id: form.corporate_id.trim() || undefined,
        consent_external_lookups: external,
        consent_corporate_registry_lookup: registry,
      });
      setResult(response);
    } catch (error) {
      setServerError(errorText(error));
    } finally {
      setSubmitting(false);
    }
  };

  const allItems = history.data?.items ?? [];
  const lowerName = form.company_name.trim().toLowerCase();
  const related = lowerName ? allItems.filter((item) => (item.company_name ?? '').toLowerCase().includes(lowerName)) : allItems;

  const columns: Array<Column<AnalysisListItem>> = [
    { key: 'company', header: 'Company / input', render: (row) => <p className="max-w-md truncate font-semibold">{row.company_name ?? row.input_preview}</p> },
    { key: 'type', header: 'Type', render: (row) => <span className="capitalize">{row.analysis_type}</span> },
    {
      key: 'risk',
      header: 'Risk',
      render: (row) => row.risk_score !== undefined && row.risk_score !== null
        ? <Badge tone={riskTone(row.risk_category)}>{row.risk_score} · {titleCase(row.risk_category ?? 'scored')}</Badge>
        : <Badge>—</Badge>,
    },
    { key: 'date', header: 'Created', render: (row) => <span className="text-muted">{relativeTime(row.created_at)}</span> },
  ];

  return (
    <div>
      <SectionHeading
        eyebrow="Entity verification"
        title="Company intelligence"
        description="Check a claimed brand or organisation and review your past investigations involving it."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <Card title="Verify a company">
          <form onSubmit={submit} noValidate className="space-y-4">
            {serverError && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{serverError}</div>}
            <Field label="Company name" htmlFor="company-name" error={errors.company_name} required>
              <input id="company-name" className="input" value={form.company_name} onChange={(event) => setForm((current) => ({ ...current, company_name: event.target.value }))} placeholder="Registered or trading name" />
            </Field>
            <Field label="Website URL" htmlFor="company-url" error={errors.website_url}>
              <input id="company-url" className="input" value={form.website_url} onChange={(event) => setForm((current) => ({ ...current, website_url: event.target.value }))} placeholder="https://… (optional)" />
            </Field>
            <Field label="Corporate registration ID" htmlFor="company-id">
              <input id="company-id" className="input" value={form.corporate_id} onChange={(event) => setForm((current) => ({ ...current, corporate_id: event.target.value }))} placeholder="Optional" />
            </Field>
            <div className="space-y-2 rounded-xl border border-line bg-elevated/50 p-4 text-sm">
              <label className="flex items-start gap-2.5">
                <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand-600" checked={external} onChange={(event) => setExternal(event.target.checked)} />
                <span>Allow external public-source lookups</span>
              </label>
              <label className="flex items-start gap-2.5">
                <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand-600" checked={registry} onChange={(event) => setRegistry(event.target.checked)} />
                <span>Allow corporate registry lookup</span>
              </label>
            </div>
            <button className="btn-primary w-full" type="submit" disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Search className="h-4 w-4" /> Verify company</>}
            </button>
          </form>
        </Card>

        <Card title="Verification result">
          {result ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-safe"><CheckCircle2 className="h-4 w-4" /> Verification response received</div>
              <dl className="space-y-2">
                {Object.entries(result).map(([key, value]) => (
                  <div key={key} className="rounded-xl border border-line bg-elevated/40 p-3">
                    <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted">{titleCase(key)}</dt>
                    <dd className="mt-1 break-words text-sm">
                      {typeof value === 'object' && value !== null ? (
                        <pre className="overflow-x-auto text-[11px]">{JSON.stringify(value, null, 2)}</pre>
                      ) : typeof value === 'boolean' ? (
                        <Badge tone={value ? 'safe' : 'warn'}>{value ? 'Yes' : 'No'}</Badge>
                      ) : (
                        String(value)
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs text-muted">Verification results are signals, not guarantees. Corroborate with primary sources.</p>
            </div>
          ) : (
            <EmptyState
              icon={<Building2 className="h-5 w-5" />}
              title="No verification run yet"
              description="Enter a company name and optional sources to see the verification response here."
            />
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Previous investigations" subtitle={lowerName ? `Companies matching “${form.company_name}”` : 'Your most recent investigations'}>
        {history.loading ? <Spinner /> : history.error ? <ErrorState message={history.error} onRetry={() => void history.refetch()} /> : (
          <DataTable
            columns={columns}
            rows={related.slice(0, 10)}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/app/reports/${row.id}`)}
            emptyTitle="No related investigations"
            emptyDescription="Analyses that mention this company will appear here."
            compact
          />
        )}
      </Card>

      <p className="mt-6 flex items-center gap-2 text-xs text-muted">
        <ShieldCheck className="h-4 w-4" /> Checking a specific offer or message? <Link className="link" to="/app/scan">Run a verification scan</Link> to include domain, brand and message intelligence. <ExternalLink className="h-3 w-3" /> Results are timestamped {formatDateTime(new Date().toISOString())}.
      </p>
    </div>
  );
}

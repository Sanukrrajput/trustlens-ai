import React, { useState } from 'react';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, fmt, num, PageHeader, StatusBadge } from '../components/Ui';

const jobColumns = [
  { key: 'started_at', label: 'Started', render: (row) => <span className="muted">{fmt(row.started_at)}</span> },
  { key: 'source', label: 'Source', render: (row) => <span className="mono">{row.source}</span> },
  {
    key: 'success',
    label: 'Result',
    render: (row) => <StatusBadge value={row.success ? 'low' : 'high'}>{row.success ? 'success' : 'failed'}</StatusBadge>,
  },
  { key: 'records_read', label: 'Read', render: (row) => num(row.records_read) },
  { key: 'records_inserted', label: 'Inserted', render: (row) => num(row.records_inserted) },
  { key: 'duplicates', label: 'Duplicates', render: (row) => num(row.duplicates) },
  { key: 'duration_ms', label: 'Duration', render: (row) => (row.duration_ms !== undefined ? `${row.duration_ms} ms` : '—') },
  {
    key: 'errors',
    label: 'Errors',
    render: (row) => (row.errors?.length ? <span className="text-danger" title={row.errors.join('\n')}>{row.errors.length}</span> : '—'),
  },
];

function toneFor(status) {
  if (status === 'healthy') return 'ok';
  if (status === 'disabled') return 'bad';
  return 'warn';
}

export default function Sources() {
  const sources = useApi(endpoints.sources);
  const jobs = useApi(endpoints.jobs);
  const action = useAsyncAction();
  const [result, setResult] = useState(null);

  const refreshAll = () => {
    sources.refetch();
    jobs.refetch();
  };

  const collect = async (name) => {
    setResult(null);
    try {
      const data = await action.run(() => api(endpoints.collect(name), { method: 'POST' }));
      setResult(data);
      refreshAll();
    } catch {
      /* surfaced through action.error */
    }
  };

  const toggle = async (name, patch) => {
    setResult(null);
    try {
      await action.run(() => api(`${endpoints.sources}/${encodeURIComponent(name)}`, { method: 'PATCH', body: patch }));
      refreshAll();
    } catch {
      /* surfaced through action.error */
    }
  };

  return (
    <>
      <PageHeader
        title="Data Collection Status"
        subtitle="Authorized, availability-checked ingestion sources and their recent collection jobs"
        actions={<button className="btn btn-sm btn-primary" onClick={refreshAll}>↻ Refresh</button>}
      />

      {action.error && <ErrorBox message={action.error} />}
      {result && (
        <div className="alert alert-secondary small">
          {result.source}: {result.success ? 'collection succeeded' : 'collection reported errors'} ·{' '}
          {num(result.records_read)} read / {num(result.records_inserted)} inserted / {num(result.duplicates)} duplicates
          {result.errors?.length ? ` · ${result.errors.length} error(s)` : ''}
        </div>
      )}
      {sources.error && <ErrorBox message={sources.error} onRetry={sources.refetch} />}

      <div className="row g-3 mb-3">
        {(sources.data?.items || []).map((source) => {
          const cursorLast = source.cursors?.last_event_at;
          return (
            <div className="col-lg-6" key={source.name}>
              <Card
                title={
                  <span className="d-flex align-items-center gap-2">
                    <span className={`badge-soft ${toneFor(source.status)}`}>● {source.status || 'unknown'}</span>
                    <span className="mono">{source.name}</span>
                  </span>
                }
              >
                <div className="detail-grid mb-3">
                  <div className="detail-item"><div className="detail-label">Type</div><div className="mt-1 mono">{source.source_type || '—'}</div></div>
                  <div className="detail-item"><div className="detail-label">Authorized</div><div className="mt-1">{source.authorized ? 'yes' : 'no'}</div></div>
                  <div className="detail-item"><div className="detail-label">Enabled</div><div className="mt-1">{source.enabled ? 'yes' : 'no'}</div></div>
                  <div className="detail-item"><div className="detail-label">Available</div><div className="mt-1">{source.available ? 'yes' : 'no'}</div></div>
                  <div className="detail-item"><div className="detail-label">Last checked</div><div className="mt-1">{fmt(source.last_checked_at)}</div></div>
                  <div className="detail-item"><div className="detail-label">Last success</div><div className="mt-1">{fmt(source.last_success_at)}</div></div>
                  <div className="detail-item"><div className="detail-label">Cursor</div><div className="mt-1">{fmt(cursorLast)}</div></div>
                  <div className="detail-item"><div className="detail-label">Events stored</div><div className="mt-1">{num(source.total_events_collected ?? source.records_inserted)}</div></div>
                </div>
                {source.reason && <p className="muted small">{source.reason}</p>}
                {source.last_error && <p className="small text-danger mb-2">{source.last_error}</p>}
                <div className="d-flex flex-wrap gap-2 mt-3">
                  <button className="btn btn-sm btn-primary" onClick={() => collect(source.name)} disabled={action.loading}>
                    {action.loading ? 'Running…' : 'Run collection now'}
                  </button>
                  <button
                    className="btn btn-sm btn-outline-light"
                    onClick={() => toggle(source.name, { enabled: !source.enabled, authorized: source.authorized })}
                    disabled={action.loading}
                  >
                    {source.enabled ? 'Disable source' : 'Enable source'}
                  </button>
                  <button
                    className="btn btn-sm btn-outline-light"
                    onClick={() => toggle(source.name, { enabled: source.enabled, authorized: !source.authorized })}
                    disabled={action.loading}
                  >
                    {source.authorized ? 'Revoke authorization' : 'Mark authorized'}
                  </button>
                </div>
              </Card>
            </div>
          );
        })}
        {!sources.loading && !sources.data?.items?.length && (
          <div className="col-12"><Card><div className="empty-box">No ingestion sources registered.</div></Card></div>
        )}
      </div>

      <Card title="Recent collection jobs">
        {jobs.error ? (
          <ErrorBox message={jobs.error} onRetry={jobs.refetch} />
        ) : (
          <DataTable
            columns={jobColumns}
            rows={jobs.data?.items || []}
            loading={jobs.loading}
            total={jobs.data?.total}
            rowKey={(row, index) => row.job_id || `${row.source}-${row.started_at}-${index}`}
            emptyMessage="No collection jobs recorded yet."
          />
        )}
      </Card>

      <p className="muted small mt-3 mb-0">
        Only sources explicitly listed as authorized and enabled are queried. Source availability and permissions are
        checked before any read; untrusted or unauthorized sources are never contacted.
      </p>
    </>
  );
}

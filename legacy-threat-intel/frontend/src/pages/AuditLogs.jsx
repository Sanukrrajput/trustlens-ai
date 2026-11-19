import React, { useState } from 'react';
import { endpoints } from '../api';
import { useApi } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, fmt, PageHeader } from '../components/Ui';

const columns = [
  { key: 'timestamp', label: 'Time', render: (row) => <span className="muted">{fmt(row.timestamp)}</span> },
  { key: 'actor', label: 'Actor', render: (row) => <span className="mono">{row.actor}</span> },
  { key: 'action', label: 'Action', render: (row) => <span className="mono">{row.action}</span> },
  {
    key: 'details',
    label: 'Details',
    render: (row) => <span title={JSON.stringify(row.details)}>{Object.entries(row.details || {}).map(([key, value]) => `${key}=${value}`).join(', ') || '—'}</span>,
  },
];

export default function AuditLogs() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [actor, setActor] = useState('');
  const [selected, setSelected] = useState(null);

  const params = { page, page_size: pageSize, q: search, actor };
  const { data, loading, error, refetch } = useApi(endpoints.audit, params);

  return (
    <>
      <PageHeader
        title="Audit Logs"
        subtitle="Immutable record of analyst actions, configuration changes and response approvals"
        actions={<button className="btn btn-sm btn-primary" onClick={refetch}>↻ Refresh</button>}
      />
      <Card>
        <div className="toolbar">
          <input
            className="form-control form-control-sm"
            style={{ maxWidth: 280 }}
            placeholder="Search action or details…"
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1); }}
          />
          <input
            className="form-control form-control-sm"
            style={{ maxWidth: 160 }}
            placeholder="Actor"
            value={actor}
            onChange={(event) => { setActor(event.target.value); setPage(1); }}
          />
          <select
            className="form-select form-select-sm"
            style={{ width: 90 }}
            value={pageSize}
            onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}
          >
            {[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </div>
        {error && <ErrorBox message={error} onRetry={refetch} />}
        <DataTable
          columns={columns}
          rows={data?.items || []}
          loading={loading}
          error={null}
          page={data?.page}
          pages={data?.pages}
          total={data?.total}
          onPage={setPage}
          onRowClick={setSelected}
          rowKey={(row) => row.audit_id}
          emptyMessage="No audit records match the current filters."
        />
      </Card>

      {selected && (
        <div className="position-fixed top-0 start-0 w-100 h-100" style={{ background: 'rgba(0,0,0,.6)', zIndex: 100 }} onClick={() => setSelected(null)}>
          <div className="card position-absolute top-0 end-0 h-100 overflow-auto rounded-0" style={{ width: 'min(620px, 100vw)' }} onClick={(event) => event.stopPropagation()}>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="mb-0">Audit record</h5>
              <button className="btn btn-sm btn-outline-light" onClick={() => setSelected(null)}>✕ Close</button>
            </div>
            <div className="detail-grid mb-3">
              <div className="detail-item"><div className="detail-label">Action</div><div className="mt-1 mono">{selected.action}</div></div>
              <div className="detail-item"><div className="detail-label">Actor</div><div className="mt-1 mono">{selected.actor}</div></div>
              <div className="detail-item"><div className="detail-label">Timestamp</div><div className="mt-1">{fmt(selected.timestamp)}</div></div>
              <div className="detail-item"><div className="detail-label">Audit ID</div><div className="mt-1 mono">{selected.audit_id}</div></div>
            </div>
            <div className="card-title">Details</div>
            <pre className="json-view">{JSON.stringify(selected.details || {}, null, 2)}</pre>
          </div>
        </div>
      )}
      <style>{`table.data-table tbody tr { cursor: pointer; }`}</style>
    </>
  );
}

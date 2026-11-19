import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, PageHeader, StatusBadge, fmt } from '../components/Ui';

export default function Incidents() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [severity, setSeverity] = useState('');
  const params = { page, page_size: 25, q: search, status, severity };
  const { data, loading, error, refetch } = useApi(endpoints.incidents, params);
  const action = useAsyncAction();

  const updateStatus = (incidentId, nextStatus) => {
    action
      .run(() => api(`/core/incidents/${encodeURIComponent(incidentId)}/status`, {
        method: 'PATCH',
        body: { status: nextStatus, note: 'Updated from dashboard' },
      }))
      .then(refetch)
      .catch(() => {});
  };

  const columns = [
    { key: 'incident_id', label: 'Incident', render: (row) => <span className="mono">{row.incident_id}</span> },
    { key: 'title', label: 'Title', sortKey: 'last_seen', render: (row) => <span title={row.description}>{row.title}</span> },
    { key: 'severity', label: 'Severity', sortKey: 'severity', render: (row) => <StatusBadge value={row.severity} /> },
    { key: 'risk_score', label: 'Risk', sortKey: 'risk_score', render: (row) => <strong>{row.risk_score}</strong> },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge value={row.status}>{row.status}</StatusBadge> },
    { key: 'events', label: 'Events', render: (row) => (row.related_event_ids || row.event_ids || []).length },
    { key: 'last_seen', label: 'Last seen', sortKey: 'last_seen', render: (row) => <span className="muted">{fmt(row.last_seen)}</span> },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div className="d-flex gap-1" onClick={(event) => event.stopPropagation()}>
          <button className="btn btn-sm btn-outline-light" onClick={() => navigate(`/investigation?id=${row.incident_id}`)}>Investigate</button>
          <select className="form-select form-select-sm" style={{ width: 120 }} defaultValue="" onChange={(event) => { if (event.target.value) updateStatus(row.incident_id, event.target.value); }}>
            <option value="" disabled>Set status</option>
            {['investigating', 'contained', 'resolved', 'closed', 'false_positive'].map((value) => <option key={value}>{value}</option>)}
          </select>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Incident Management" subtitle="Correlated, deduplicated incidents with evidence and analyst status" actions={<button className="btn btn-sm btn-primary" onClick={refetch}>↻ Refresh</button>} />
      {action.error && <ErrorBox message={action.error} />}
      <Card>
        <div className="toolbar">
          <input className="form-control form-control-sm" style={{ maxWidth: 260 }} placeholder="Search incidents…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} />
          <select className="form-select form-select-sm" style={{ width: 160 }} value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            {['new', 'investigating', 'contained', 'resolved', 'closed', 'false_positive'].map((value) => <option key={value}>{value}</option>)}
          </select>
          <select className="form-select form-select-sm" style={{ width: 160 }} value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
            <option value="">All severities</option>
            {['critical', 'high', 'medium', 'low', 'informational'].map((value) => <option key={value}>{value}</option>)}
          </select>
          <Link className="small" to="/investigation">Open investigation workspace →</Link>
        </div>
        {error && <ErrorBox message={error} onRetry={refetch} />}
        <DataTable
          columns={columns}
          rows={data?.items || []}
          loading={loading}
          page={data?.page}
          pages={data?.pages}
          total={data?.total}
          onPage={setPage}
          rowKey={(row) => row.incident_id}
          onRowClick={(row) => navigate(`/investigation?id=${row.incident_id}`)}
        />
      </Card>
    </>
  );
}

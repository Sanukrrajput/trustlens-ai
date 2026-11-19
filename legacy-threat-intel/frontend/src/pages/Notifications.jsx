import React, { useState } from 'react';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, fmt, PageHeader, StatusBadge } from '../components/Ui';

const columns = (onMarkRead, loading) => [
  { key: 'created_at', label: 'Time', render: (row) => <span className="muted">{fmt(row.created_at)}</span> },
  { key: 'severity', label: 'Severity', render: (row) => <StatusBadge value={row.severity} /> },
  { key: 'title', label: 'Title' },
  {
    key: 'message',
    label: 'Message',
    render: (row) => <span title={row.message}>{(row.message || '').slice(0, 90)}</span>,
  },
  {
    key: 'incident_id',
    label: 'Incident',
    render: (row) => <span className="mono">{row.incident_id || '—'}</span>,
  },
  {
    key: 'read',
    label: 'Status',
    render: (row) => (row.read
      ? <StatusBadge value="low">read</StatusBadge>
      : <StatusBadge value="high">unread</StatusBadge>),
  },
  {
    key: 'action',
    label: '',
    render: (row) => (row.read ? '—' : (
      <button
        className="btn btn-sm btn-outline-light"
        disabled={loading}
        onClick={(event) => { event.stopPropagation(); onMarkRead(row.notification_id); }}
      >
        Mark read
      </button>
    )),
  },
];

export default function Notifications() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [severity, setSeverity] = useState('');
  const [selected, setSelected] = useState(null);

  const params = { page, page_size: pageSize, unread_only: unreadOnly, severity };
  const { data, loading, error, refetch } = useApi(endpoints.notifications, params);
  const action = useAsyncAction();

  const markRead = async (notificationId) => {
    try {
      await action.run(() => api(`${endpoints.notifications}/${encodeURIComponent(notificationId)}/read`, { method: 'POST' }));
      setSelected(null);
      refetch();
    } catch {
      /* surfaced through action.error */
    }
  };

  return (
    <>
      <PageHeader
        title="Notification Center"
        subtitle="Alert notifications generated from correlated incidents; delivery history is deduplicated"
        actions={<button className="btn btn-sm btn-primary" onClick={refetch}>↻ Refresh</button>}
      />

      <Card>
        <div className="toolbar">
          <div className="form-check">
            <input
              className="form-check-input"
              type="checkbox"
              id="unreadOnly"
              checked={unreadOnly}
              onChange={(event) => { setUnreadOnly(event.target.checked); setPage(1); }}
            />
            <label className="form-check-label small" htmlFor="unreadOnly">Unread only</label>
          </div>
          <select
            className="form-select form-select-sm"
            style={{ width: 150 }}
            value={severity}
            onChange={(event) => { setSeverity(event.target.value); setPage(1); }}
          >
            <option value="">All severities</option>
            {['critical', 'high', 'medium', 'low', 'info'].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select
            className="form-select form-select-sm"
            style={{ width: 90 }}
            value={pageSize}
            onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}
          >
            {[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </div>
        {action.error && <ErrorBox message={action.error} />}
        {error && <ErrorBox message={error} onRetry={refetch} />}
        <DataTable
          columns={columns(markRead, action.loading)}
          rows={data?.items || []}
          loading={loading}
          error={null}
          page={data?.page}
          pages={data?.pages}
          total={data?.total}
          onPage={setPage}
          onRowClick={setSelected}
          rowKey={(row) => row.notification_id}
          emptyMessage="No notifications match the current filters."
        />
      </Card>

      {selected && (
        <div className="position-fixed top-0 start-0 w-100 h-100" style={{ background: 'rgba(0,0,0,.6)', zIndex: 100 }} onClick={() => setSelected(null)}>
          <div className="card position-absolute top-0 end-0 h-100 overflow-auto rounded-0" style={{ width: 'min(560px, 100vw)' }} onClick={(event) => event.stopPropagation()}>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="mb-0">Notification detail</h5>
              <button className="btn btn-sm btn-outline-light" onClick={() => setSelected(null)}>✕ Close</button>
            </div>
            <h6>{selected.title}</h6>
            <p className="small">{selected.message}</p>
            <div className="detail-grid">
              <div className="detail-item"><div className="detail-label">Severity</div><div className="mt-1"><StatusBadge value={selected.severity} /></div></div>
              <div className="detail-item"><div className="detail-label">Incident</div><div className="mt-1 mono">{selected.incident_id || '—'}</div></div>
              <div className="detail-item"><div className="detail-label">Created</div><div className="mt-1">{fmt(selected.created_at)}</div></div>
              <div className="detail-item"><div className="detail-label">Read</div><div className="mt-1">{selected.read ? fmt(selected.read_at) : 'no'}</div></div>
              <div className="detail-item"><div className="detail-label">Channels</div><div className="mt-1">{(selected.channels || []).join(', ') || 'dashboard'}</div></div>
            </div>
            {!selected.read && (
              <button className="btn btn-sm btn-primary mt-3" onClick={() => markRead(selected.notification_id)} disabled={action.loading}>
                Mark as read
              </button>
            )}
          </div>
        </div>
      )}
      <style>{`table.data-table tbody tr { cursor: pointer; }`}</style>
    </>
  );
}

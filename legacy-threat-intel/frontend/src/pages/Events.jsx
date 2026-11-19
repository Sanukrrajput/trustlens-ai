import React, { useState } from 'react';
import { endpoints } from '../api';
import { useApi } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, fmt, KeyValue, PageHeader } from '../components/Ui';

const columns = [
  { key: 'timestamp', label: 'Time', sortKey: 'timestamp', render: (row) => <span className="muted">{fmt(row.timestamp)}</span> },
  { key: 'event_type', label: 'Event type', sortKey: 'event_type', render: (row) => <span className="mono">{row.event_type}</span> },
  { key: 'source_type', label: 'Source' },
  { key: 'actor_user', label: 'User', render: (row) => row.actor_user || '—' },
  { key: 'source_ip', label: 'Source IP', sortKey: 'source_ip', render: (row) => <span className="mono">{row.source_ip || '—'}</span> },
  { key: 'destination_host', label: 'Destination', render: (row) => row.destination_host || row.destination_ip || '—' },
  { key: 'host', label: 'Host' },
  { key: 'message', label: 'Message', render: (row) => <span title={row.message}>{(row.message || '').slice(0, 60)}</span> },
];

export default function Events() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [eventType, setEventType] = useState('');
  const [sourceIp, setSourceIp] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sort, setSort] = useState('timestamp');
  const [order, setOrder] = useState('desc');
  const [selected, setSelected] = useState(null);

  const params = { page, page_size: pageSize, q: search, event_type: eventType, source_ip: sourceIp, date_from: dateFrom, date_to: dateTo, sort, order };
  const { data, loading, error, refetch } = useApi(endpoints.events, params);

  const changeSort = (field) => {
    if (sort === field) setOrder(order === 'asc' ? 'desc' : 'asc');
    else { setSort(field); setOrder('desc'); }
  };

  return (
    <>
      <PageHeader title="Live Security Events" subtitle="Normalized, deduplicated events from authorized sources" actions={<button className="btn btn-sm btn-primary" onClick={refetch}>↻ Refresh</button>} />
      <Card>
        <div className="toolbar">
          <input className="form-control form-control-sm" style={{ maxWidth: 260 }} placeholder="Search events…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} />
          <input className="form-control form-control-sm" style={{ maxWidth: 180 }} placeholder="Event type" value={eventType} onChange={(event) => { setEventType(event.target.value); setPage(1); }} />
          <input className="form-control form-control-sm" style={{ maxWidth: 150 }} placeholder="Source IP" value={sourceIp} onChange={(event) => { setSourceIp(event.target.value); setPage(1); }} />
          <input className="form-control form-control-sm" type="date" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} />
          <input className="form-control form-control-sm" type="date" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} />
          <select className="form-select form-select-sm" style={{ width: 90 }} value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
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
          sort={sort}
          order={order}
          onSort={changeSort}
          onRowClick={setSelected}
          rowKey={(row) => row.event_id}
        />
      </Card>

      {selected && (
        <div className="position-fixed top-0 start-0 w-100 h-100" style={{ background: 'rgba(0,0,0,.6)', zIndex: 100 }} onClick={() => setSelected(null)}>
          <div className="card position-absolute top-0 end-0 h-100 overflow-auto rounded-0" style={{ width: 'min(620px, 100vw)' }} onClick={(event) => event.stopPropagation()}>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="mb-0">Event detail</h5>
              <button className="btn btn-sm btn-outline-light" onClick={() => setSelected(null)}>✕ Close</button>
            </div>
            <KeyValue items={[
              { label: 'Event ID', value: <span className="mono">{selected.event_id}</span> },
              { label: 'Timestamp', value: fmt(selected.timestamp) },
              { label: 'Type', value: selected.event_type },
              { label: 'Source', value: `${selected.source_type || ''} / ${selected.source_name || ''}` },
              { label: 'User', value: selected.actor_user },
              { label: 'Source IP', value: selected.source_ip },
              { label: 'Destination', value: selected.destination_ip || selected.destination_host },
              { label: 'Asset', value: selected.asset_id },
              { label: 'Message', value: selected.message },
            ]} />
            <div className="card-title mt-4">Raw record (redacted)</div>
            <pre className="json-view">{JSON.stringify(selected, null, 2)}</pre>
          </div>
        </div>
      )}
      <style>{`table.data-table tbody tr { cursor: pointer; }`}</style>
    </>
  );
}

import React, { useState } from 'react';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, fmt, PageHeader, StatusBadge } from '../components/Ui';

const columns = [
  { key: 'normalized_value', label: 'Indicator', sortKey: 'last_seen', render: (row) => <span className="mono">{row.normalized_value}</span> },
  { key: 'type', label: 'Type', render: (row) => <StatusBadge>{row.type}</StatusBadge> },
  { key: 'reputation', label: 'Reputation', render: (row) => <StatusBadge value={row.reputation}>{row.reputation}</StatusBadge> },
  { key: 'confidence', label: 'Confidence', render: (row) => `${Math.round((row.confidence || 0) * 100)}%` },
  { key: 'sources', label: 'Sources', render: (row) => (row.sources || []).map((s) => s.name).join(', ') || 'local' },
  { key: 'first_seen', label: 'First seen', render: (row) => <span className="muted">{fmt(row.first_seen)}</span> },
  { key: 'last_seen', label: 'Last seen', sortKey: 'last_seen', render: (row) => <span className="muted">{fmt(row.last_seen)}</span> },
];

const titles = {
  all: ['Threat Intelligence', 'Indicators observed in authorized events and cached feed evidence'],
  ip: ['Suspicious IP Explorer', 'IPv4/IPv6 reputation from local cache and configured feeds'],
  domain: ['Domain & URL Intelligence', 'Domain and URL reputation evidence'],
};

export default function Indicators({ mode = 'all' }) {
  const [title, subtitle] = titles[mode];
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [maliciousOnly, setMaliciousOnly] = useState(false);
  const [kind, setKind] = useState('');
  const [enrichType, setEnrichType] = useState('ip');
  const [enrichValue, setEnrichValue] = useState('');
  const [force, setForce] = useState(false);
  const [notice, setNotice] = useState(null);
  const enrichAction = useAsyncAction();

  const effectiveKind = kind || (mode === 'ip' ? 'ipv4,ipv6' : mode === 'domain' ? 'domain,url' : '');
  const params = { page, page_size: 25, q: search, kind: effectiveKind, malicious_only: maliciousOnly || undefined };
  const { data, loading, error, refetch } = useApi(endpoints.indicators, params);

  const submitEnrichment = async (event) => {
    event.preventDefault();
    setNotice(null);
    try {
      const result = await enrichAction.run(() => api(endpoints.enrich, { method: 'POST', params: { force }, body: { type: enrichType, value: enrichValue } }));
      setNotice(result.external_lookup ? 'External lookup completed and cached.' : 'Cached locally; no external lookup performed.');
      refetch();
    } catch {
      /* error shown by action state */
    }
  };

  return (
    <>
      <PageHeader title={title} subtitle={subtitle} actions={<button className="btn btn-sm btn-primary" onClick={refetch}>↻ Refresh</button>} />
      {notice && <div className="alert alert-info py-2 small">{notice}</div>}
      <div className="row g-3 mb-3">
        <div className="col-lg-9">
          <Card>
            <div className="toolbar">
              <input className="form-control form-control-sm" style={{ maxWidth: 260 }} placeholder="Search indicator…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} />
              <select className="form-select form-select-sm" style={{ width: 150 }} value={kind} onChange={(event) => { setKind(event.target.value); setPage(1); }}>
                <option value="">All configured types</option>
                <option value="ipv4">IPv4</option>
                <option value="ipv6">IPv6</option>
                <option value="domain">Domain</option>
                <option value="url">URL</option>
                <option value="hash">Hash</option>
              </select>
              <div className="form-check form-switch small">
                <input className="form-check-input" type="checkbox" id="maliciousOnly" checked={maliciousOnly} onChange={(event) => { setMaliciousOnly(event.target.checked); setPage(1); }} />
                <label className="form-check-label" htmlFor="maliciousOnly">Malicious only</label>
              </div>
            </div>
            {error && <ErrorBox message={error} onRetry={refetch} />}
            <DataTable columns={columns} rows={data?.items || []} loading={loading} page={data?.page} pages={data?.pages} total={data?.total} onPage={setPage} rowKey={(row) => row.indicator_id} />
          </Card>
        </div>
        <div className="col-lg-3">
          <Card title="Enrich indicator">
            <form onSubmit={submitEnrichment}>
              <label className="form-label small">Type</label>
              <select className="form-select form-select-sm mb-2" value={enrichType} onChange={(event) => setEnrichType(event.target.value)}>
                {['ip', 'ipv4', 'ipv6', 'domain', 'url', 'md5', 'sha1', 'sha256'].map((type) => <option key={type}>{type}</option>)}
              </select>
              <label className="form-label small">Value</label>
              <input className="form-control form-control-sm mb-2" value={enrichValue} onChange={(event) => setEnrichValue(event.target.value)} placeholder="198.51.100.77" required />
              <div className="form-check small mb-3">
                <input className="form-check-input" type="checkbox" id="forceEnrich" checked={force} onChange={(event) => setForce(event.target.checked)} />
                <label className="form-check-label" htmlFor="forceEnrich">Force refresh cache</label>
              </div>
              <button className="btn btn-sm btn-primary w-100" disabled={enrichAction.loading}>
                {enrichAction.loading ? 'Querying…' : 'Enrich'}
              </button>
              {enrichAction.error && <div className="error-box mt-2 small">{enrichAction.error}</div>}
              <p className="muted small mt-3 mb-0">Private/internal indicators are cached locally and never transmitted to external feeds.</p>
            </form>
          </Card>
        </div>
      </div>
    </>
  );
}

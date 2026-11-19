import React, { useState } from 'react';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import { Card, ErrorBox, PageHeader, StatusBadge } from '../components/Ui';

export default function Assets() {
  const { data, loading, error, refetch } = useApi(endpoints.assets);
  const action = useAsyncAction();
  const [form, setForm] = useState({ asset_id: '', hostname: '', ip_addresses: '', criticality: 3, owner: '' });

  const submit = async (event) => {
    event.preventDefault();
    try {
      await action.run(() => api(endpoints.assets, {
        method: 'POST',
        body: {
          asset_id: form.asset_id,
          hostname: form.hostname,
          ip_addresses: form.ip_addresses.split(',').map((value) => value.trim()).filter(Boolean),
          criticality: Number(form.criticality),
          owner: form.owner,
        },
      }));
      refetch();
      setForm({ asset_id: '', hostname: '', ip_addresses: '', criticality: 3, owner: '' });
    } catch {
      /* shown below */
    }
  };

  return (
    <>
      <PageHeader title="Monitored Assets" subtitle="Authorized asset inventory used for criticality-weighted risk scoring" />
      <div className="row g-3">
        <div className="col-lg-8">
          <Card>
            {error ? <ErrorBox message={error} onRetry={refetch} /> : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>Asset ID</th><th>Hostname</th><th>IP addresses</th><th>Criticality</th><th>Owner</th></tr></thead>
                  <tbody>
                    {(data?.items || []).map((asset) => (
                      <tr key={asset.asset_id}>
                        <td className="mono">{asset.asset_id}</td>
                        <td>{asset.hostname || '—'}</td>
                        <td className="mono">{(asset.ip_addresses || []).join(', ') || '—'}</td>
                        <td><StatusBadge value={Number(asset.criticality) >= 4 ? 'high' : 'low'}>{asset.criticality}/5</StatusBadge></td>
                        <td>{asset.owner || '—'}</td>
                      </tr>
                    ))}
                    {!loading && !data?.items?.length && <tr><td colSpan="5" className="empty-box">No assets registered yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
            {loading && <div className="muted small">Loading…</div>}
          </Card>
        </div>
        <div className="col-lg-4">
          <Card title="Register / update asset">
            <form onSubmit={submit}>
              {[
                ['asset_id', 'Asset ID'],
                ['hostname', 'Hostname'],
                ['ip_addresses', 'IP addresses (comma separated)'],
                ['owner', 'Owner / team'],
              ].map(([key, label]) => (
                <div className="mb-2" key={key}>
                  <label className="form-label small">{label}</label>
                  <input className="form-control form-control-sm" value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} required={key === 'asset_id'} />
                </div>
              ))}
              <label className="form-label small">Criticality (0–5)</label>
              <input className="form-control form-control-sm mb-3" type="number" min="0" max="5" value={form.criticality} onChange={(event) => setForm({ ...form, criticality: event.target.value })} />
              <button className="btn btn-sm btn-primary w-100" disabled={action.loading}>{action.loading ? 'Saving…' : 'Save asset'}</button>
              {action.error && <ErrorBox message={action.error} />}
            </form>
          </Card>
        </div>
      </div>
    </>
  );
}

import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import { Card, ErrorBox, fmt, Loading, PageHeader, StatusBadge } from '../components/Ui';

export default function Investigation() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get('id') || '';
  const [actionType, setActionType] = useState('block_ip');
  const [target, setTarget] = useState('');
  const [rationale, setRationale] = useState('');
  const [note, setNote] = useState('');
  const [message, setMessage] = useState(null);
  const action = useAsyncAction();

  const incidents = useApi(endpoints.incidents, { page: 1, page_size: 100 });
  const investigation = useApi(selectedId ? endpoints.investigation(selectedId) : null, {}, [selectedId]);
  const actions = useApi(endpoints.actions);

  useEffect(() => {
    if (!selectedId && incidents.data?.items?.length) {
      setSearchParams({ id: incidents.data.items[0].incident_id });
    }
  }, [selectedId, incidents.data, setSearchParams]);

  useEffect(() => {
    const first = investigation.data?.sections?.find((section) => section.key === 'indicators')?.content || '';
    const match = first.match(/(?:ipv4|ipv6):([^\s(,]+)/);
    if (match) setTarget(match[1]);
  }, [investigation.data]);

  const propose = async (event) => {
    event.preventDefault();
    setMessage(null);
    try {
      await action.run(() => api(endpoints.actions, {
        method: 'POST',
        body: { incident_id: selectedId, action_type: actionType, target, rationale, requested_by: 'analyst' },
      }));
      setMessage('Response action proposed. It is pending explicit approval and has not been executed.');
      actions.refetch();
    } catch {
      /* displayed by action state */
    }
  };

  const approve = async (actionId) => {
    setMessage(null);
    try {
      await action.run(() => api(`${endpoints.actions}/${actionId}/approve`, { method: 'POST', params: { approver: 'analyst', note } }));
      setMessage('Approval recorded in audit_logs. The platform does not execute disruptive actions.');
      actions.refetch();
    } catch {
      /* displayed by action state */
    }
  };

  return (
    <>
      <PageHeader title="Incident Investigation" subtitle="Structured explanations generated from MongoDB evidence only" />
      <div className="row g-3">
        <div className="col-lg-4">
          <Card title="Select incident">
            <select className="form-select form-select-sm" value={selectedId} onChange={(event) => setSearchParams({ id: event.target.value })}>
              <option value="">Choose an incident…</option>
              {(incidents.data?.items || []).map((incident) => (
                <option key={incident.incident_id} value={incident.incident_id}>
                  {incident.incident_id} · {incident.severity} · {incident.title?.slice(0, 34)}
                </option>
              ))}
            </select>
            {incidents.loading && <div className="muted small mt-2">Loading incidents…</div>}
            {incidents.error && <ErrorBox message={incidents.error} />}
            {selectedId && investigation.data?.evidence_counts && (
              <div className="mt-3">
                <div className="detail-item mb-2"><div className="detail-label">Evidence</div>
                  {Object.entries(investigation.data.evidence_counts).map(([key, value]) => (
                    <div key={key} className="d-flex justify-content-between small"><span className="muted">{key.replace('_', ' ')}</span><span>{value}</span></div>
                  ))}
                </div>
                <div className="small muted">Generated {fmt(investigation.data.generated_at)}</div>
              </div>
            )}
          </Card>

          <Card title="Response workflow" className="mt-3">
            <p className="muted small">Read-only by default. Proposals and approvals are logged; no blocking or account changes are executed.</p>
            <form onSubmit={propose}>
              <select className="form-select form-select-sm mb-2" value={actionType} onChange={(event) => setActionType(event.target.value)}>
                {['block_ip', 'disable_account', 'isolate_asset', 'reset_credentials', 'custom'].map((value) => <option key={value}>{value}</option>)}
              </select>
              <input className="form-control form-control-sm mb-2" placeholder="Target" value={target} onChange={(event) => setTarget(event.target.value)} required />
              <input className="form-control form-control-sm mb-2" placeholder="Rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />
              <button className="btn btn-sm btn-outline-light w-100" disabled={!selectedId || action.loading}>Propose action</button>
            </form>
            {(actions.data?.items || []).length > 0 && (
              <div className="mt-3">
                <div className="card-title">Pending actions</div>
                {(actions.data?.items || []).filter((item) => item.status === 'pending_approval').map((item) => (
                  <div key={item.action_id} className="detail-item mb-2 small">
                    <div className="mono">{item.action_type} → {item.target}</div>
                    <input className="form-control form-control-sm my-2" placeholder="Approval note" value={note} onChange={(event) => setNote(event.target.value)} />
                    <button className="btn btn-sm btn-outline-light" onClick={() => approve(item.action_id)} disabled={action.loading}>Record approval</button>
                  </div>
                ))}
              </div>
            )}
            {message && <div className="alert alert-secondary py-2 small mt-3 mb-0">{message}</div>}
            {action.error && <ErrorBox message={action.error} />}
          </Card>
        </div>

        <div className="col-lg-8">
          {!selectedId ? <Card><div className="empty-box">Select an incident to generate its investigation brief.</div></Card>
            : investigation.loading ? <Card><Loading /></Card>
              : investigation.error ? <Card><ErrorBox message={investigation.error} onRetry={investigation.refetch} /></Card>
                : (
                  <Card title={`Investigation brief · ${selectedId}`} action={<StatusBadge value={investigation.data.sections ? 'evidence-based' : 'unknown'}>evidence-based</StatusBadge>}>
                    {(investigation.data.sections || []).map((section) => (
                      <div className="explain-section" key={section.key}>
                        <h6>{section.title}</h6>
                        <div className="small">{section.content}</div>
                      </div>
                    ))}
                    <div className="muted small border-top pt-3 mt-3">{investigation.data.disclaimer}</div>
                  </Card>
                )}
        </div>
      </div>
    </>
  );
}

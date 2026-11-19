import React, { useState } from 'react';
import { endpoints } from '../api';
import { useApi } from '../hooks';
import DataTable from '../components/Table';
import { Card, ErrorBox, fmt, PageHeader, StatusBadge } from '../components/Ui';

const columns = [
  { key: 'created_at', label: 'Detected at', sortKey: 'created_at', render: (row) => <span className="muted">{fmt(row.created_at)}</span> },
  { key: 'title', label: 'Anomaly', sortKey: 'title' },
  { key: 'severity', label: 'Severity', render: (row) => <StatusBadge value={row.severity} /> },
  { key: 'score', label: 'Anomaly score', render: (row) => row.raw_signals?.anomaly_score ?? row.risk_score ?? '—' },
  { key: 'risk_score', label: 'Risk', sortKey: 'risk_score', render: (row) => <strong>{row.risk_score}</strong> },
  { key: 'model_version', label: 'Model', render: (row) => <span className="mono">{row.model_version || '—'}</span> },
  { key: 'confidence', label: 'Confidence', render: (row) => `${Math.round((row.confidence || 0) * 100)}%` },
  { key: 'events', label: 'Events', render: (row) => (row.event_ids || []).length },
  { key: 'reasons', label: 'Reason', render: (row) => <span title={(row.detection_reasons || []).join('; ')}>{(row.detection_reasons || [])[0]?.slice(0, 55) || '—'}</span> },
];

export default function Anomalies() {
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState('');
  const [minScore, setMinScore] = useState('');
  const params = { page, page_size: 25, detection_type: 'ml', severity, min_score: minScore };
  const { data, loading, error, refetch } = useApi(endpoints.detections, params);
  const models = useApi(endpoints.models);
  const untrained = (models.data?.items || []).filter((m) => m.status === 'untrained').length;

  return (
    <>
      <PageHeader title="AI Anomaly Detection" subtitle="Isolation Forest and Random Forest detections with clear model provenance" actions={<button className="btn btn-sm btn-primary" onClick={refetch}>↻ Refresh</button>} />
      {untrained > 0 && (
        <div className="alert alert-warning py-2 small">
          {untrained} model(s) are not yet trained. ML inference is inactive; rule-based detection remains fully operational.
          Train models only after verified labeled data is available.
        </div>
      )}
      <Card>
        <div className="toolbar">
          <select className="form-select form-select-sm" style={{ width: 170 }} value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
            <option value="">All severities</option>
            {['critical', 'high', 'medium', 'low', 'informational'].map((item) => <option key={item}>{item}</option>)}
          </select>
          <input className="form-control form-control-sm" style={{ width: 150 }} type="number" min="0" max="100" placeholder="Min risk score" value={minScore} onChange={(event) => { setMinScore(event.target.value); setPage(1); }} />
        </div>
        {error && <ErrorBox message={error} onRetry={refetch} />}
        <DataTable columns={columns} rows={data?.items || []} loading={loading} page={data?.page} pages={data?.pages} total={data?.total} onPage={setPage} rowKey={(row) => row.detection_id} emptyMessage="No ML detections. Models may be untrained or no anomalies crossed the threshold." />
      </Card>
    </>
  );
}

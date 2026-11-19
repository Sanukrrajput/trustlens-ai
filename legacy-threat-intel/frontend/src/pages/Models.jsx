import React from 'react';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import { Card, ErrorBox, fmt, PageHeader, StatusBadge } from '../components/Ui';

export default function Models() {
  const { data, loading, error, refetch } = useApi(endpoints.models);
  const action = useAsyncAction();

  const train = async () => {
    try {
      await action.run(() => api(endpoints.train, { method: 'POST' }));
      refetch();
    } catch {
      /* shown below */
    }
  };

  const result = action.data;
  return (
    <>
      <PageHeader
        title="ML Model Performance"
        subtitle="Versioned models with grouped train/test split and honest metrics"
        actions={<button className="btn btn-sm btn-primary" onClick={train} disabled={action.loading}>{action.loading ? 'Training…' : 'Train from labeled data'}</button>}
      />
      {action.error && <ErrorBox message={action.error} />}
      {result && (
        <div className="alert alert-secondary small">
          {result.status === 'trained'
            ? `Trained version ${result.version}; ${result.train_groups} train groups / ${result.test_groups} test groups.`
            : result.message || `Training not started: ${result.status}`}
        </div>
      )}
      {error && <ErrorBox message={error} onRetry={refetch} />}
      <div className="row g-3">
        {(data?.items || []).map((model) => {
          const metrics = model.metrics || {};
          return (
            <div className="col-lg-6" key={`${model.name}-${model.version}`}>
              <Card title={<span>{model.name} <StatusBadge value={model.status}>{model.status}</StatusBadge></span>}>
                <div className="detail-grid mb-3">
                  <div className="detail-item"><div className="detail-label">Version</div><div className="mono mt-1">{model.version}</div></div>
                  <div className="detail-item"><div className="detail-label">Type</div><div className="mt-1">{model.model_type || '—'}</div></div>
                  <div className="detail-item"><div className="detail-label">Active</div><div className="mt-1">{model.is_active ? 'yes' : 'no'}</div></div>
                  <div className="detail-item"><div className="detail-label">Trained</div><div className="mt-1">{fmt(model.trained_at)}</div></div>
                </div>
                <div className="card-title">Holdout metrics</div>
                <div className="detail-grid">
                  {['precision', 'recall', 'f1', 'false_positive_rate'].map((key) => (
                    <div className="detail-item" key={key}>
                      <div className="detail-label">{key.replace('_', ' ')}</div>
                      <div className="mt-1">{metrics[key] !== undefined ? Number(metrics[key]).toFixed(3) : '—'}</div>
                    </div>
                  ))}
                </div>
                <p className="muted small mt-3 mb-0">
                  {model.status === 'untrained'
                    ? 'No validated labeled data available. ML inference is disabled and rules continue operating.'
                    : model.note || 'Scores are not calibrated probabilities; analyst verification is required.'}
                </p>
              </Card>
            </div>
          );
        })}
        {!loading && !data?.items?.length && <div className="col-12"><Card><div className="empty-box">No models registered.</div></Card></div>}
      </div>
    </>
  );
}

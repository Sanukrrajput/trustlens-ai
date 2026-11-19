import React, { useEffect, useState } from 'react';
import { api, endpoints } from '../api';
import { useApi, useAsyncAction } from '../hooks';
import { Card, ErrorBox, fmt, num, PageHeader, StatusBadge } from '../components/Ui';

const THRESHOLD_FIELDS = [
  { key: 'rule_failed_login_threshold', label: 'Failed logins before alert', type: 'number' },
  { key: 'rule_failure_window_minutes', label: 'Failure window (min)', type: 'number' },
  { key: 'rule_brute_force_accounts', label: 'Brute-force accounts', type: 'number' },
  { key: 'rule_brute_force_threshold', label: 'Brute-force threshold', type: 'number' },
  { key: 'rule_success_after_failures', label: 'Success after failures', type: 'number' },
  { key: 'rule_success_after_failures_window_minutes', label: 'Success-after window (min)', type: 'number' },
  { key: 'rule_unusual_hours_start', label: 'Unusual hours start', type: 'number' },
  { key: 'rule_unusual_hours_end', label: 'Unusual hours end', type: 'number' },
  { key: 'rule_api_rate_threshold', label: 'API rate threshold', type: 'number' },
  { key: 'rule_malicious_confidence', label: 'Malicious confidence', type: 'number', step: '0.01' },
  { key: 'critical_asset_criticality', label: 'Critical asset criticality', type: 'number' },
  { key: 'ml_min_train_samples', label: 'ML min train samples', type: 'number' },
  { key: 'risk_weight_ti', label: 'Risk weight · threat intel', type: 'number', step: '0.01' },
  { key: 'risk_weight_ml', label: 'Risk weight · ML anomaly', type: 'number', step: '0.01' },
  { key: 'risk_weight_rule', label: 'Risk weight · rule severity', type: 'number', step: '0.01' },
  { key: 'risk_weight_asset', label: 'Risk weight · asset criticality', type: 'number', step: '0.01' },
  { key: 'risk_weight_correlation', label: 'Risk weight · correlation', type: 'number', step: '0.01' },
  { key: 'correlation_window_hours', label: 'Correlation window (h)', type: 'number' },
  { key: 'alert_min_severity', label: 'Minimum alert severity', type: 'text' },
  { key: 'ti_cache_ttl_hours', label: 'TI cache TTL (h)', type: 'number' },
  { key: 'ti_rate_limit_per_minute', label: 'TI rate limit / min', type: 'number' },
  { key: 'ti_feed_max_records', label: 'TI feed max records', type: 'number' },
];

const ENVIRONMENT_FIELDS = [
  'environment', 'log_level', 'auth_enabled', 'scheduler_enabled', 'change_stream_enabled',
  'collection_interval_minutes', 'detection_interval_minutes', 'enrichment_interval_minutes',
  'correlation_interval_minutes', 'health_interval_minutes', 'authorized_sources',
  'enabled_sources', 'windows_eventlog_channels', 'windows_eventlog_event_ids',
  'windows_eventlog_max_events', 'windows_eventlog_lookback_minutes', 'ti_enabled',
  'ti_cache_ttl_hours', 'ti_rate_limit_per_minute', 'event_retention_days',
  'detection_retention_days', 'incident_retention_days', 'notification_retention_days',
  'audit_retention_days', 'job_retention_days', 'alert_min_severity', 'alert_emails',
  'smtp_host', 'smtp_port', 'smtp_from', 'webhook_url', 'response_actions_enabled',
  'model_dir', 'if_contamination', 'api_key', 'abuseipdb_api_key', 'urlhaus_api_key',
  'smtp_password', 'webhook_secret',
];

function displayValue(value) {
  if (value === null || value === undefined) return '—';
  if (Array.isArray(value)) return value.join(', ') || '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function Settings() {
  const settings = useApi(endpoints.settings);
  const health = useApi(endpoints.health);
  const action = useAsyncAction();
  const [form, setForm] = useState({});

  useEffect(() => {
    const environment = settings.data?.environment || {};
    const overrides = settings.data?.runtime_thresholds || {};
    const initial = {};
    THRESHOLD_FIELDS.forEach(({ key }) => {
      const value = overrides[key] !== undefined ? overrides[key] : environment[key];
      initial[key] = value !== undefined && value !== null ? String(value) : '';
    });
    setForm(initial);
  }, [settings.data]);

  const save = async (event) => {
    event.preventDefault();
    const overrides = {};
    THRESHOLD_FIELDS.forEach(({ key, type }) => {
      if (form[key] === undefined || form[key] === '') return;
      overrides[key] = type === 'number' ? Number(form[key]) : form[key];
    });
    try {
      await action.run(() => api(endpoints.settings, { method: 'PUT', body: { overrides } }));
      settings.refetch();
    } catch {
      /* surfaced through action.error */
    }
  };

  const environment = settings.data?.environment || {};
  const scheduler = health.data?.scheduler || {};
  const database = health.data?.database || {};

  return (
    <>
      <PageHeader
        title="System Settings"
        subtitle="Runtime detection thresholds, environment configuration and live system health"
        actions={<button className="btn btn-sm btn-primary" onClick={() => { settings.refetch(); health.refetch(); }}>↻ Refresh</button>}
      />

      {settings.error && <ErrorBox message={settings.error} onRetry={settings.refetch} />}
      {health.error && <ErrorBox message={health.error} onRetry={health.refetch} />}
      {action.error && <ErrorBox message={action.error} />}
      {action.data?.status === 'updated' && <div className="alert alert-secondary small">Thresholds saved; new detections will use these values.</div>}

      <div className="row g-3">
        <div className="col-lg-7">
          <Card title="Runtime detection thresholds">
            {settings.loading ? <div className="muted small">Loading…</div> : (
              <form onSubmit={save}>
                <div className="row g-2">
                  {THRESHOLD_FIELDS.map(({ key, label, type, step }) => (
                    <div className="col-md-6" key={key}>
                      <label className="form-label small mb-1">{label}</label>
                      <input
                        className="form-control form-control-sm"
                        type={type}
                        step={step}
                        value={form[key] ?? ''}
                        onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                      />
                    </div>
                  ))}
                </div>
                <button className="btn btn-sm btn-primary mt-3" disabled={action.loading || settings.loading}>
                  {action.loading ? 'Saving…' : 'Save thresholds'}
                </button>
                <p className="muted small mt-2 mb-0">
                  Changes apply to future detection and scoring runs. Every update is recorded in the audit log.
                </p>
              </form>
            )}
          </Card>
        </div>

        <div className="col-lg-5">
          <Card title="System health">
            {health.loading ? <div className="muted small">Loading…</div> : (
              <>
                <div className="detail-grid">
                  <div className="detail-item"><div className="detail-label">Overall</div><div className="mt-1"><StatusBadge value={health.data?.status}>{health.data?.status || '—'}</StatusBadge></div></div>
                  <div className="detail-item"><div className="detail-label">Database</div><div className="mt-1">{displayValue(database.status)}</div></div>
                  <div className="detail-item"><div className="detail-label">Version</div><div className="mt-1 mono">{health.data?.version || '—'}</div></div>
                  <div className="detail-item"><div className="detail-label">Uptime</div><div className="mt-1">{num(health.data?.uptime_seconds)} s</div></div>
                  <div className="detail-item"><div className="detail-label">Scheduler</div><div className="mt-1">{scheduler.running ? 'running' : (scheduler.enabled ? 'enabled' : 'stopped')}</div></div>
                  <div className="detail-item"><div className="detail-label">Last check</div><div className="mt-1">{fmt(health.data?.recorded_at)}</div></div>
                </div>
                <div className="card-title mt-3">Record counts</div>
                <div className="detail-grid">
                  {Object.entries(health.data?.counts || {}).map(([key, value]) => (
                    <div className="detail-item" key={key}>
                      <div className="detail-label">{key.replace(/_/g, ' ')}</div>
                      <div className="mt-1">{num(value)}</div>
                    </div>
                  ))}
                </div>
                {scheduler.jobs && (
                  <>
                    <div className="card-title mt-3">Scheduled jobs</div>
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead><tr><th>Job</th><th>Interval</th><th>Next run</th></tr></thead>
                        <tbody>
                          {scheduler.jobs.map((job) => (
                            <tr key={job.name || job.id}>
                              <td className="mono">{job.name || job.id}</td>
                              <td>{displayValue(job.interval_minutes ?? job.trigger)}</td>
                              <td>{fmt(job.next_run_time)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </>
            )}
          </Card>
        </div>

        <div className="col-lg-12">
          <Card title="Environment configuration (secrets masked)">
            {settings.loading ? <div className="muted small">Loading…</div> : (
              <div className="detail-grid">
                {ENVIRONMENT_FIELDS.filter((key) => environment[key] !== undefined).map((key) => (
                  <div className="detail-item" key={key}>
                    <div className="detail-label">{key.replace(/_/g, ' ')}</div>
                    <div className="mt-1 mono" style={{ wordBreak: 'break-all' }}>{displayValue(environment[key])}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="col-lg-12">
          <Card title="Source authorization state">
            {settings.loading ? <div className="muted small">Loading…</div> : (
              <div className="detail-grid">
                {Object.entries(settings.data?.source_toggles || {}).map(([name, value]) => (
                  <div className="detail-item" key={name}>
                    <div className="detail-label mono">{name}</div>
                    <div className="mt-1">enabled: {value?.enabled ? 'yes' : 'no'} · authorized: {value?.authorized ? 'yes' : 'no'}</div>
                  </div>
                ))}
                {!Object.keys(settings.data?.source_toggles || {}).length && (
                  <div className="muted small">No per-source overrides recorded; environment defaults apply.</div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>

      <p className="muted small mt-3 mb-0">
        Secrets are never returned in plain text. Edit environment variables and restart the backend to change
        credentials or deployment-level settings.
      </p>
    </>
  );
}

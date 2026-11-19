import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { endpoints } from '../api';
import { useApi } from '../hooks';
import { Card, ErrorBox, Loading, PageHeader, StatCard, StatusBadge, fmt, num } from '../components/Ui';
import { BarDistribution, DistributionChart, TimeSeriesChart } from '../components/Charts';

export default function Overview() {
  const [days, setDays] = useState(7);
  const summary = useApi(endpoints.summary);
  const timeseries = useApi(endpoints.eventsOverTime, { days }, [days]);
  const data = summary.data || {};

  return (
    <>
      <PageHeader
        title="Security Operations Overview"
        subtitle="Live MongoDB-backed telemetry, detections and incident posture"
        actions={
          <>
            <select className="form-select form-select-sm" style={{ width: 120 }} value={days} onChange={(event) => setDays(Number(event.target.value))}>
              <option value={1}>Last 24h</option>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
            </select>
            <button className="btn btn-sm btn-primary" onClick={() => { summary.refetch(); timeseries.refetch(); }}>↻ Refresh</button>
          </>
        }
      />

      {summary.error && <ErrorBox message={summary.error} onRetry={summary.refetch} />}

      <div className="row g-3 mb-3">
        <div className="col-6 col-lg-3"><StatCard label="Total security events" value={num(data.total_security_events)} tone="accent" /></div>
        <div className="col-6 col-lg-3"><StatCard label="Active incidents" value={num(data.active_incidents)} tone="amber" /></div>
        <div className="col-6 col-lg-3"><StatCard label="High-risk detections" value={num(data.high_risk_detections)} tone="red" /></div>
        <div className="col-6 col-lg-3"><StatCard label="Critical alerts" value={num(data.critical_alerts)} tone="red" /></div>
        <div className="col-6 col-lg-3"><StatCard label="Suspicious IPs" value={num(data.suspicious_ip_count)} tone="accent" /></div>
      </div>

      {summary.loading ? <Loading /> : (
        <>
          <div className="row g-3 mb-3">
            <div className="col-lg-7">
              <Card title={`Security events over time · ${days}d`}>
                {timeseries.loading ? <Loading /> : timeseries.error ? <ErrorBox message={timeseries.error} onRetry={timeseries.refetch} /> : <TimeSeriesChart data={timeseries.data} />}
              </Card>
            </div>
            <div className="col-lg-5">
              <Card title="Threat category distribution">
                <DistributionChart data={data.threat_category_distribution || []} />
              </Card>
            </div>
            <div className="col-lg-6">
              <Card title="Detection source breakdown">
                <BarDistribution data={data.detection_source_breakdown || []} color="#4cc9f0" />
              </Card>
            </div>
            <div className="col-lg-6">
              <Card title="Incident severity distribution">
                <DistributionChart data={data.incident_severity_distribution || []} />
              </Card>
            </div>
          </div>

          <div className="row g-3">
            <div className="col-lg-7">
              <Card title="Recent incidents" action={<Link className="small" to="/incidents">View all →</Link>}>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead><tr><th>Incident</th><th>Severity</th><th>Risk</th><th>Status</th><th>Last seen</th></tr></thead>
                    <tbody>
                      {(data.recent_incidents || []).map((incident) => (
                        <tr key={incident.incident_id}>
                          <td title={incident.title}>{incident.title?.slice(0, 62) || '—'}</td>
                          <td><StatusBadge value={incident.severity} /></td>
                          <td>{incident.risk_score ?? '—'}</td>
                          <td>{incident.status || '—'}</td>
                          <td className="muted">{fmt(incident.last_seen)}</td>
                        </tr>
                      ))}
                      {!data.recent_incidents?.length && <tr><td colSpan="5" className="empty-box">No incidents correlated yet.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
            <div className="col-lg-5">
              <Card title="Data source health" action={<Link className="small" to="/collection">Details →</Link>}>
                <div className="table-wrap">
                  <table className="data-table">
                    <thead><tr><th>Source</th><th>Status</th><th>Detail</th></tr></thead>
                    <tbody>
                      {(data.data_source_health || []).map((source) => (
                        <tr key={source.name}>
                          <td className="mono">{source.name}</td>
                          <td><StatusBadge value={source.status}>{source.status}</StatusBadge></td>
                          <td className="muted" title={source.reason}>{source.reason?.slice(0, 60) || '—'}</td>
                        </tr>
                      ))}
                      {!data.data_source_health?.length && <tr><td colSpan="3" className="empty-box">No source status recorded yet.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}

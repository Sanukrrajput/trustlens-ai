import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { api, endpoints } from '../api';

const navigation = [
  {
    group: 'Operations',
    items: [
      { to: '/', label: 'Overview', icon: '▣', end: true },
      { to: '/events', label: 'Live Events', icon: '≋' },
      { to: '/incidents', label: 'Incidents', icon: '⚑' },
      { to: '/investigation', label: 'Investigation', icon: '⌕' },
    ],
  },
  {
    group: 'Intelligence',
    items: [
      { to: '/threat-intelligence', label: 'Threat Intelligence', icon: '◈' },
      { to: '/suspicious-ips', label: 'Suspicious IPs', icon: '⊞' },
      { to: '/domain-intelligence', label: 'Domain & URL', icon: '⛓' },
      { to: '/anomalies', label: 'AI Anomaly Detection', icon: '◇' },
    ],
  },
  {
    group: 'Assets & Models',
    items: [
      { to: '/assets', label: 'Monitored Assets', icon: '▤' },
      { to: '/models', label: 'ML Model Performance', icon: '◉' },
    ],
  },
  {
    group: 'Automation & Governance',
    items: [
      { to: '/collection', label: 'Data Collection Status', icon: '⟳' },
      { to: '/notifications', label: 'Notification Center', icon: '✉' },
      { to: '/audit', label: 'Audit Logs', icon: '≡' },
      { to: '/settings', label: 'System Settings', icon: '⚙' },
    ],
  },
];

export default function Layout() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [clock, setClock] = useState(new Date());
  const navigate = useNavigate();

  const refresh = () => {
    api(endpoints.status)
      .then((data) => { setStatus(data); setError(null); })
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(() => {
      setClock(new Date());
      refresh();
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  const healthy = status?.database?.status === 'healthy' && !error;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">TI</div>
          <div>
            <div className="brand-title">SOC Intelligence</div>
            <div className="brand-sub">THREAT PLATFORM</div>
          </div>
        </div>
        {navigation.map((section) => (
          <div key={section.group}>
            <div className="nav-group">{section.group}</div>
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              >
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="d-flex align-items-center gap-3">
            <span className={`badge-soft ${healthy ? 'ok' : 'bad'}`}>
              ● {healthy ? 'SYSTEM ONLINE' : 'DEGRADED'}
            </span>
            <span className="muted small d-none d-sm-inline">
              {status?.scheduler?.running ? 'Automation active' : 'Automation inactive'} · {status?.environment || 'unknown'}
            </span>
          </div>
          <div className="d-flex align-items-center gap-3">
            <span className="muted small d-none d-md-inline">{clock.toLocaleTimeString()}</span>
            <button className="btn btn-sm btn-outline-light" onClick={refresh}>↻ Refresh</button>
            <button className="btn btn-sm btn-outline-light" onClick={() => navigate('/notifications')}>Notifications</button>
          </div>
        </header>
        <main className="page"><Outlet /></main>
      </div>
    </div>
  );
}

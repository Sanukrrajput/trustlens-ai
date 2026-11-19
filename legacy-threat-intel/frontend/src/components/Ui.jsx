import React from 'react';

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="d-flex flex-wrap justify-content-between align-items-end gap-2 mb-3">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      <div className="d-flex gap-2">{actions}</div>
    </div>
  );
}

export function Card({ title, action, children, className = '' }) {
  return (
    <div className={`card ${className}`}>
      {(title || action) && (
        <div className="card-title">
          <span>{title}</span>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatCard({ label, value, sub, tone = 'accent' }) {
  const colors = {
    accent: 'var(--accent)',
    red: 'var(--red)',
    amber: 'var(--amber)',
    green: 'var(--green)',
  };
  return (
    <div className="card stat-card" style={{ '--tint': `${colors[tone]}1c` }}>
      <div className="stat-label mb-2">{label}</div>
      <div className="stat-value" style={{ color: colors[tone] }}>{value ?? '—'}</div>
      {sub && <div className="stat-label mt-2">{sub}</div>}
    </div>
  );
}

export function StatusBadge({ value, children }) {
  const text = String(value ?? children ?? 'unknown');
  const className = `badge-soft sev-${text.toLowerCase().replace(/[^a-z]/g, '')}`;
  return <span className={className}>{children || text}</span>;
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading-box">
      <span className="spinner-border spinner-border-sm text-info" role="status" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div className="error-box d-flex justify-content-between align-items-center gap-3">
      <span>{message}</span>
      {onRetry && <button className="btn btn-sm btn-outline-light" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Empty({ message = 'No records found for the current filters.' }) {
  return <div className="empty-box">{message}</div>;
}

export function Pagination({ page = 1, pages = 1, total = 0, onPage }) {
  if (!pages || pages <= 1) return <div className="muted small mt-2">{total} record(s)</div>;
  const items = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);
  for (let index = start; index <= end; index += 1) items.push(index);
  return (
    <div className="d-flex justify-content-between align-items-center mt-3">
      <span className="muted small">{total} record(s) · page {page} of {pages}</span>
      <nav>
        <ul className="pagination pagination-sm mb-0">
          <li className={`page-item ${page <= 1 ? 'disabled' : ''}`}>
            <button className="page-link" onClick={() => onPage(page - 1)}>‹</button>
          </li>
          {items.map((item) => (
            <li key={item} className={`page-item ${item === page ? 'active' : ''}`}>
              <button className="page-link" onClick={() => onPage(item)}>{item}</button>
            </li>
          ))}
          <li className={`page-item ${page >= pages ? 'disabled' : ''}`}>
            <button className="page-link" onClick={() => onPage(page + 1)}>›</button>
          </li>
        </ul>
      </nav>
    </div>
  );
}

export function KeyValue({ items }) {
  return (
    <div className="detail-grid">
      {items.filter((item) => item.value !== undefined && item.value !== null).map((item) => (
        <div className="detail-item" key={item.label}>
          <div className="detail-label">{item.label}</div>
          <div className="mt-1">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function fmt(value, fallback = '—') {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export function num(value) {
  return typeof value === 'number' ? value.toLocaleString() : value ?? '—';
}

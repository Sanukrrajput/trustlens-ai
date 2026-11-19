import React from 'react';
import { Empty, Loading, ErrorBox, Pagination } from './Ui';

export default function DataTable({
  columns,
  rows = [],
  rowKey = (row) => row._id || row.event_id || row.incident_id || row.notification_id || row.indicator_id,
  loading,
  error,
  onRetry,
  page,
  pages,
  total,
  onPage,
  sort,
  order,
  onSort,
  onRowClick,
  emptyMessage,
}) {
  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={onRetry} />;
  if (!rows.length) return <Empty message={emptyMessage} />;

  return (
    <>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => {
                const sortable = Boolean(column.sortKey && onSort);
                return (
                  <th
                    key={column.key}
                    className={sortable ? 'sortable' : ''}
                    onClick={sortable ? () => onSort(column.sortKey) : undefined}
                  >
                    {column.label}
                    {sortable && sort === column.sortKey ? (order === 'asc' ? ' ↑' : ' ↓') : ''}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={rowKey(row, index)} onClick={onRowClick ? () => onRowClick(row) : undefined}>
                {columns.map((column) => (
                  <td key={column.key}>
                    {column.render ? column.render(row, index) : (row[column.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {onPage && <Pagination page={page} pages={pages} total={total} onPage={onPage} />}
    </>
  );
}

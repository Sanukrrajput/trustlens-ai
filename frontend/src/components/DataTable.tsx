import type { ReactNode } from 'react';
import { cx } from '../lib/utils';
import { EmptyState, Spinner } from './ui';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
  headerClassName?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  emptyTitle = 'Nothing here yet',
  emptyDescription,
  onRowClick,
  compact = false,
}: {
  columns: Array<Column<T>>;
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRowClick?: (row: T) => void;
  compact?: boolean;
}) {
  if (loading) return <Spinner label="Loading records…" />;
  if (!rows.length) return <EmptyState title={emptyTitle} description={emptyDescription} />;

  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-[600px] text-left text-sm">
        <thead className="bg-elevated text-[11px] uppercase tracking-wider text-muted">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={cx('px-4 py-3 font-semibold', column.headerClassName)}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-surface">
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={cx('transition hover:bg-elevated/60', onRowClick && 'cursor-pointer')}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} className={cx(compact ? 'px-4 py-2.5' : 'px-4 py-3.5', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

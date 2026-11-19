import { Link } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { cx } from '../lib/utils';

export function Logo({ to = '/', compact = false, className }: { to?: string; compact?: boolean; className?: string }) {
  return (
    <Link to={to} className={cx('inline-flex items-center gap-2.5', className)} aria-label="HireShield AI home">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-700 text-white shadow-[0_8px_20px_-8px_rgba(8,145,178,0.9)]">
        <ShieldCheck className="h-5 w-5" aria-hidden="true" />
      </span>
      {!compact && (
        <span className="leading-tight">
          <span className="block text-sm font-extrabold tracking-tight">HireShield<span className="text-brand-500"> AI</span></span>
          <span className="block text-[10px] font-medium uppercase tracking-[0.18em] text-muted">Risk intelligence</span>
        </span>
      )}
    </Link>
  );
}

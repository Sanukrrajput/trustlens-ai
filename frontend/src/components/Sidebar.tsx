import { NavLink } from 'react-router-dom';
import {
  Building2,
  CreditCard,
  LayoutDashboard,
  Radar,
  ScanSearch,
  Settings,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { cx } from '../lib/utils';
import { Logo } from './Logo';

const links = [
  { to: '/app', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/app/scan', label: 'New scan', icon: ScanSearch },
  { to: '/app/company', label: 'Company intelligence', icon: Building2 },
  { to: '/app/monitoring', label: 'Job monitoring', icon: Radar },
  { to: '/app/billing', label: 'Plans & billing', icon: CreditCard },
  { to: '/app/settings', label: 'Settings', icon: Settings },
];

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, isAdmin } = useAuth();

  return (
    <>
      {open && <button aria-label="Close navigation" className="fixed inset-0 z-40 bg-slate-950/60 lg:hidden" onClick={onClose} />}
      <aside
        className={cx(
          'fixed inset-y-0 left-0 z-50 flex w-[17rem] flex-col border-r border-line bg-surface transition-transform duration-200 lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-line px-5">
          <Logo to="/app" />
          <button className="rounded-lg p-1.5 text-muted hover:bg-elevated lg:hidden" onClick={onClose} aria-label="Close sidebar">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-5">
          <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-muted">Workspace</p>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              onClick={onClose}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition',
                  isActive ? 'bg-brand-500/10 text-brand-700 dark:text-brand-300' : 'text-muted hover:bg-elevated hover:text-ink',
                )
              }
            >
              <link.icon className="h-[1.1rem] w-[1.1rem]" />
              {link.label}
            </NavLink>
          ))}

          {isAdmin && (
            <>
              <p className="mb-2 mt-6 px-3 text-[10px] font-bold uppercase tracking-[0.2em] text-muted">Administration</p>
              <NavLink
                to="/app/admin"
                onClick={onClose}
                className={({ isActive }) =>
                  cx(
                    'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition',
                    isActive ? 'bg-brand-500/10 text-brand-700 dark:text-brand-300' : 'text-muted hover:bg-elevated hover:text-ink',
                  )
                }
              >
                <ShieldCheck className="h-[1.1rem] w-[1.1rem]" />
                Admin console
              </NavLink>
            </>
          )}
        </nav>

        <div className="border-t border-line p-4">
          <div className="flex items-center gap-3 rounded-xl bg-elevated p-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600/15 text-xs font-bold text-brand-700 dark:text-brand-300">
              {user?.full_name?.slice(0, 2).toUpperCase() ?? 'HS'}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{user?.full_name ?? 'Guest'}</p>
              <p className="truncate text-xs text-muted">{user?.email ?? 'Not signed in'}</p>
              <p className="mt-1 inline-flex rounded-full bg-brand-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-brand-700 dark:text-brand-300">
                {isAdmin ? 'Administrator' : 'User'}
              </p>
            </div>
          </div>
          <p className="mt-3 px-1 text-[10px] text-muted">Evidence-led decisions. Never guaranteed outcomes.</p>
        </div>
      </aside>
    </>
  );
}

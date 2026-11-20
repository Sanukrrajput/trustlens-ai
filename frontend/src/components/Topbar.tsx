import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Bell, LogOut, Menu, Moon, Plus, Sun, UserRound } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useApi } from '../hooks/useApi';
import { notificationsApi, unwrapList } from '../lib/api';

const titles: Record<string, string> = {
  '/app': 'Overview',
  '/app/scan': 'New scan',
  '/app/company': 'Company intelligence',
  '/app/monitoring': 'Job monitoring',
  '/app/billing': 'Plans & billing',
  '/app/settings': 'Settings',
  '/app/admin': 'Admin console',
};

export function Topbar({ onOpenSidebar }: { onOpenSidebar: () => void }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const { data } = useApi(() => notificationsApi.list().then(unwrapList), []);
  const unread = (data ?? []).filter((item) => !item.read).length;

  const title = pathname.startsWith('/app/reports/')
    ? 'Investigation report'
    : titles[pathname] ?? 'TrustLens AI';

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur-xl sm:px-6">
      <button className="rounded-lg p-2 text-muted hover:bg-elevated lg:hidden" onClick={onOpenSidebar} aria-label="Open navigation">
        <Menu className="h-5 w-5" />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-base font-bold sm:text-lg">{title}</h1>
        <p className="hidden text-xs text-muted sm:block">Secure workspace · {user?.organisation ?? 'Personal account'}</p>
      </div>

      <Link to="/app/scan" className="btn-primary hidden sm:inline-flex">
        <Plus className="h-4 w-4" /> New scan
      </Link>

      <button
        onClick={toggleTheme}
        className="rounded-xl border border-line bg-surface p-2.5 text-muted transition hover:text-ink"
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>

      <Link
        to="/app/settings"
        className="relative rounded-xl border border-line bg-surface p-2.5 text-muted transition hover:text-ink"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{unread > 9 ? '9+' : unread}</span>}
      </Link>

      <div className="relative">
        <button
          className="flex items-center gap-2 rounded-xl border border-line bg-surface p-1.5 pr-2 text-sm"
          onClick={() => setMenuOpen((value) => !value)}
          aria-expanded={menuOpen}
          aria-label="Account menu"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600/15 text-brand-700 dark:text-brand-300">
            <UserRound className="h-4 w-4" />
          </span>
          <span className="hidden max-w-28 truncate md:block">{user?.full_name ?? 'Account'}</span>
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-12 w-56 rounded-xl border border-line bg-surface p-1.5 shadow-card">
            <div className="border-b border-line px-3 py-2">
              <p className="truncate text-sm font-semibold">{user?.full_name}</p>
              <p className="truncate text-xs text-muted">{user?.email}</p>
            </div>
            <Link to="/app/settings" className="block rounded-lg px-3 py-2 text-sm hover:bg-elevated" onClick={() => setMenuOpen(false)}>
              Settings & notifications
            </Link>
            <button
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-danger/10"
              onClick={async () => {
                setMenuOpen(false);
                await logout();
                navigate('/login');
              }}
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

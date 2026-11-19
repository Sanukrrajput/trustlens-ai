import { useState } from 'react';
import { Link, Outlet } from 'react-router-dom';
import { Github, Menu, ShieldCheck, X } from 'lucide-react';
import { Logo } from './Logo';
import { useTheme } from '../context/ThemeContext';
import { Moon, Sun } from 'lucide-react';

export function PublicLayout() {
  const [open, setOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6 lg:px-8">
          <Logo />
          <nav className="ml-6 hidden items-center gap-6 text-sm font-medium text-muted md:flex">
            <a className="hover:text-ink" href="/#capabilities">Capabilities</a>
            <a className="hover:text-ink" href="/#pricing">Pricing</a>
            <a className="hover:text-ink" href="/#faq">FAQ</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={toggleTheme}
              className="rounded-xl border border-line p-2 text-muted hover:text-ink"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <Link to="/login" className="btn-ghost hidden sm:inline-flex">Sign in</Link>
            <Link to="/register" className="btn-primary">Get started</Link>
            <button className="rounded-xl p-2 text-muted md:hidden" onClick={() => setOpen((value) => !value)} aria-label="Toggle menu">
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
        {open && (
          <nav className="border-t border-line bg-surface px-4 py-3 md:hidden">
            {[
              ['Capabilities', '/#capabilities'],
              ['Pricing', '/#pricing'],
              ['FAQ', '/#faq'],
            ].map(([label, href]) => (
              <a key={label} href={href} className="block rounded-lg px-3 py-2 text-sm text-muted hover:bg-elevated" onClick={() => setOpen(false)}>
                {label}
              </a>
            ))}
            <Link to="/login" className="block rounded-lg px-3 py-2 text-sm text-muted hover:bg-elevated">Sign in</Link>
          </nav>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-4 lg:px-8">
          <div>
            <Logo />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-muted">
              Evidence-led job fraud risk intelligence. We surface signals and confidence — never certainty.
            </p>
          </div>
          <div>
            <p className="mb-3 text-xs font-bold uppercase tracking-wider text-ink">Product</p>
            <ul className="space-y-2 text-sm text-muted">
              <li><Link className="hover:text-brand-500" to="/app/scan">Scanner</Link></li>
              <li><Link className="hover:text-brand-500" to="/app/company">Company intelligence</Link></li>
              <li><Link className="hover:text-brand-500" to="/app/monitoring">Monitoring</Link></li>
              <li><Link className="hover:text-brand-500" to="/#pricing">Pricing</Link></li>
            </ul>
          </div>
          <div>
            <p className="mb-3 text-xs font-bold uppercase tracking-wider text-ink">Legal</p>
            <ul className="space-y-2 text-sm text-muted">
              <li><Link className="hover:text-brand-500" to="/privacy">Privacy policy</Link></li>
              <li><Link className="hover:text-brand-500" to="/terms">Terms of service</Link></li>
              <li><span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> Privacy-first design</span></li>
            </ul>
          </div>
          <div>
            <p className="mb-3 text-xs font-bold uppercase tracking-wider text-ink">Trust</p>
            <p className="text-sm leading-relaxed text-muted">
              Inconclusive results are reported honestly. Every indicator carries provenance, confidence and limitations.
            </p>
            <span className="mt-4 inline-flex items-center gap-2 text-xs text-muted"><Github className="h-4 w-4" /> Built for informed decisions</span>
          </div>
        </div>
        <div className="border-t border-line px-4 py-5 text-center text-xs text-muted">
          © {new Date().getFullYear()} HireShield AI. This product does not guarantee that any listing, employer or recruiter is legitimate.
        </div>
      </footer>
    </div>
  );
}

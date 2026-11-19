import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Check, Fingerprint, ScanSearch, ShieldCheck } from 'lucide-react';
import { Logo } from '../../components/Logo';

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="grid min-h-screen bg-bg lg:grid-cols-[1.05fr_1fr]">
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-grid bg-[size:42px_42px] opacity-[0.14]" />
        <div className="absolute -right-24 top-1/4 h-96 w-96 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="relative">
          <Logo />
        </div>
        <div className="relative max-w-lg">
          <span className="chip border-white/20 bg-white/5 text-cyan-200">EVIDENCE, NOT ASSUMPTIONS</span>
          <h2 className="mt-6 text-4xl font-extrabold leading-tight tracking-tight">
            Verify before you apply.<br />Detect before you trust.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-slate-300">
            Every assessment explains what was found, what could not be verified, and how much confidence to place in the result.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-slate-200">
            {['Explainable risk scoring with source provenance', 'Corroborated indicators across domain, company and message signals', 'Explicit missing evidence and technical limitations'].map((item) => (
              <li key={item} className="flex items-start gap-3">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-cyan-300" /> {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative flex items-center gap-6 text-xs text-slate-400">
          <span className="inline-flex items-center gap-2"><Fingerprint className="h-4 w-4" /> Privacy-first</span>
          <span className="inline-flex items-center gap-2"><ScanSearch className="h-4 w-4" /> Transparent evidence</span>
          <span className="inline-flex items-center gap-2"><ShieldCheck className="h-4 w-4" /> Honest uncertainty</span>
        </div>
      </div>

      <div className="flex flex-col items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden"><Logo /></div>
          <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
          <p className="mt-2 text-sm text-muted">{subtitle}</p>
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-6 text-center text-sm text-muted">{footer}</div>}
          <p className="mt-10 text-center text-xs text-muted">
            <Link className="hover:text-ink" to="/privacy">Privacy</Link> ·{' '}
            <Link className="hover:text-ink" to="/terms">Terms</Link> · HireShield AI
          </p>
        </div>
      </div>
    </div>
  );
}

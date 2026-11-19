import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-500"><Compass className="h-7 w-7" /></span>
      <p className="mt-6 font-mono text-sm font-bold text-brand-500">404</p>
      <h1 className="mt-2 text-3xl font-bold">Page not found</h1>
      <p className="mt-3 max-w-md text-sm text-muted">The page you are looking for may have moved or does not exist.</p>
      <Link to="/" className="btn-primary mt-7">Return home</Link>
    </div>
  );
}

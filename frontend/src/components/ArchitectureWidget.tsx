import { useState } from 'react';
import { Boxes, X } from 'lucide-react';
import { ArchitectureScene3D } from './ArchitectureScene3D';

export function ArchitectureWidget() {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-5 right-5 z-[85] flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {open && (
        <div
          id="architecture-widget-panel"
          className="max-h-[calc(100vh-7rem)] w-[380px] max-w-[calc(100vw-2.5rem)] overflow-y-auto rounded-2xl border border-line bg-surface shadow-card"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted">
              <Boxes className="h-4 w-4 text-brand-500" /> Internal architecture
            </span>
            <button
              type="button"
              className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-ink"
              onClick={() => setOpen(false)}
              aria-label="Close architecture widget"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <img
            src={`${import.meta.env.BASE_URL}architecture-corner.png`}
            alt="Internal architecture illustration"
            className="h-28 w-full bg-black object-contain"
          />
          <ArchitectureScene3D />
        </div>
      )}
      <button
        type="button"
        className="relative overflow-hidden rounded-2xl border border-line bg-surface p-1.5 shadow-card transition hover:-translate-y-0.5 hover:border-brand-500"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="architecture-widget-panel"
        aria-label="Open internal architecture widget"
      >
        <img
          src={`${import.meta.env.BASE_URL}architecture-corner.png`}
          alt="Internal architecture illustration"
          className="h-28 w-20 rounded-xl bg-black object-contain"
        />
        <span className="absolute inset-x-1.5 bottom-1.5 rounded-b-xl bg-black/75 px-1 py-0.5 text-center text-[9px] font-bold uppercase tracking-wide text-white">
          Architecture
        </span>
      </button>
    </div>
  );
}

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
          <ArchitectureScene3D />
        </div>
      )}
      <button
        type="button"
        className="inline-flex items-center gap-2 rounded-full bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-card transition hover:bg-brand-600"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="architecture-widget-panel"
      >
        <Boxes className="h-4 w-4" /> Architecture
      </button>
    </div>
  );
}

import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { BrainCircuit, Database, Globe2, Layers3, ShieldCheck } from 'lucide-react';

const steps = [
  'Browser sends a typed request',
  'FastAPI validates auth, role and rate limit',
  'Repositories read and write MongoDB',
  'Approved ML plus rules assemble evidence',
  'Response returns sources and limitations',
];

export function ArchitectureScene3D() {
  const [step, setStep] = useState(0);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach((timer) => window.clearTimeout(timer)), []);

  const run = () => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current = [];
    setStep(0);
    setDone(false);
    setRunning(true);

    steps.slice(1).forEach((_, index) => {
      const timer = window.setTimeout(() => {
        setStep(index + 1);
        if (index === steps.length - 2) {
          setDone(true);
          setRunning(false);
        }
      }, 900 * (index + 1));
      timers.current.push(timer);
    });
  };

  const tilt = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    event.currentTarget.style.setProperty('--ry', `${((x - 0.5) * 16).toFixed(2)}deg`);
    event.currentTarget.style.setProperty('--rx', `${((0.5 - y) * 12).toFixed(2)}deg`);
  };

  const resetTilt = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.style.setProperty('--ry', '-10deg');
    event.currentTarget.style.setProperty('--rx', '8deg');
  };

  return (
    <div className="rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">Internal architecture</p>
          <p className="text-sm font-bold">How a request actually moves</p>
        </div>
        <span className="chip text-[10px] uppercase">Live stack</span>
      </div>

      <div className="c3d-stage">
        <div
          className={`c3d-scene ${running ? 'c3d-running' : ''} ${done ? 'c3d-done' : ''}`}
          onPointerMove={tilt}
          onPointerLeave={resetTilt}
        >
          <div className="c3d-glow" aria-hidden="true" />
          <div className="c3d-grid" aria-hidden="true" />

          <svg className="c3d-links" viewBox="0 0 430 440" preserveAspectRatio="none" aria-hidden="true">
            <path className="c3d-link" d="M180 175 C205 185 222 198 236 212" />
            <path className="c3d-pulse" d="M180 175 C205 185 222 198 236 212" />
            <path className="c3d-link" d="M238 230 C205 252 150 275 100 292" />
            <path className="c3d-pulse" d="M238 230 C205 252 150 275 100 292" />
            <path className="c3d-link" d="M140 305 C200 330 270 335 338 306" />
            <path className="c3d-pulse c3d-pulse-alt" d="M140 305 C200 330 270 335 338 306" />
            <path className="c3d-link" d="M300 190 C320 170 330 146 340 128" />
            <path className="c3d-pulse c3d-pulse-alt" d="M300 190 C320 170 330 146 340 128" />
          </svg>

          <div className="c3d-object c3d-browser" aria-hidden="true">
            <div className="c3d-browser-bar"><i /><i /><i /></div>
            <div className="c3d-browser-body">
              <Globe2 className="h-4 w-4 text-brand-500" />
              <p>React + TypeScript</p>
              <b>POST /analyses</b>
              <span className="c3d-browser-line" />
              <span className="c3d-browser-line short" />
            </div>
            <span className="c3d-label">Browser UI</span>
          </div>

          <button
            type="button"
            className="c3d-object c3d-shield"
            onClick={run}
            aria-label="Animate the internal request flow"
          >
            <span className="c3d-shield-face">
              <ShieldCheck className="h-7 w-7 text-brand-500" />
              <b>FastAPI</b>
              <small>{running ? 'Routing…' : 'Run flow'}</small>
            </span>
            <span className="c3d-label">API layer</span>
          </button>

          <div className="c3d-object c3d-repo" aria-hidden="true">
            <div className="c3d-repo-stack"><Layers3 className="h-5 w-5" /><span>Repo</span></div>
            <span className="c3d-label">Repositories</span>
          </div>

          <div className="c3d-object c3d-ml" aria-hidden="true">
            <div className="c3d-ml-chip"><BrainCircuit className="h-6 w-6" /><span>ML</span></div>
            <span className="c3d-label">Approved models</span>
          </div>

          <div className="c3d-object c3d-db" aria-hidden="true">
            <div className="c3d-db-cylinder"><i /><i /><i /></div>
            <span className="c3d-label"><Database className="mr-1 inline h-2.5 w-2.5" />MongoDB</span>
          </div>

          <div
            className="c3d-result"
            aria-live="polite"
            style={done ? { opacity: 1, transform: 'translateX(-50%) translateZ(105px) scale(1)', transition: 'none' } : undefined}
          >
            <b>Evidence response</b>
            <span>Scores · sources · limitations</span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-medium text-muted" aria-live="polite">{steps[step]}</p>
        <button type="button" className="btn-primary px-4 py-2 text-xs" onClick={run}>
          {done ? 'Replay flow' : 'Show internal flow'}
        </button>
      </div>
    </div>
  );
}

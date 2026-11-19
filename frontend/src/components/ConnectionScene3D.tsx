import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { BrainCircuit, Database, ShieldCheck, Smartphone, UserRound } from 'lucide-react';

const steps = [
  'Job seeker connects the offer',
  'HireShield checks the evidence',
  'MongoDB saves the session',
  'Approved ML explains the risk',
  'Evidence ready — not a verdict',
];

export function ConnectionScene3D() {
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
      }, 850 * (index + 1));
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
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">Interactive flow</p>
          <p className="text-sm font-bold">See how an offer connects</p>
        </div>
        <span className="chip text-[10px] uppercase">Illustrative</span>
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
            <path className="c3d-link" d="M82 235 C112 205 132 185 160 166" />
            <path className="c3d-pulse" d="M82 235 C112 205 132 185 160 166" />
            <path className="c3d-link" d="M190 180 C215 190 230 200 242 214" />
            <path className="c3d-pulse" d="M190 180 C215 190 230 200 242 214" />
            <path className="c3d-link" d="M300 190 C320 170 330 146 340 128" />
            <path className="c3d-pulse c3d-pulse-alt" d="M300 190 C320 170 330 146 340 128" />
            <path className="c3d-link" d="M302 230 C320 250 330 276 338 300" />
            <path className="c3d-pulse c3d-pulse-alt" d="M302 230 C320 250 330 276 338 300" />
          </svg>

          <div className="c3d-object c3d-person" aria-hidden="true">
            <div className="c3d-person-head"><UserRound className="h-5 w-5" /></div>
            <div className="c3d-person-body" />
            <span className="c3d-label">Job seeker</span>
          </div>

          <div className="c3d-object c3d-phone" aria-hidden="true">
            <div className="c3d-phone-screen">
              <Smartphone className="h-4 w-4 text-danger" />
              <p className="c3d-phone-alert">URGENT HIRING</p>
              <p className="c3d-phone-copy">Pay a fee today. No interview.</p>
              <span className="c3d-phone-line" />
              <span className="c3d-phone-line short" />
            </div>
            <span className="c3d-label">Suspicious offer</span>
          </div>

          <button
            type="button"
            className="c3d-object c3d-shield"
            onClick={run}
            aria-label="Connect the suspicious offer to HireShield"
          >
            <span className="c3d-shield-face">
              <ShieldCheck className="h-7 w-7 text-brand-500" />
              <b>HireShield</b>
              <small>{running ? 'Checking…' : 'Tap to connect'}</small>
            </span>
            <span className="c3d-label">App</span>
          </button>

          <div className="c3d-object c3d-ml" aria-hidden="true">
            <div className="c3d-ml-chip"><BrainCircuit className="h-6 w-6" /><span>ML</span></div>
            <span className="c3d-label">Approved model</span>
          </div>

          <div className="c3d-object c3d-db" aria-hidden="true">
            <div className="c3d-db-cylinder"><i /><i /><i /></div>
            <span className="c3d-label"><Database className="mr-1 inline h-2.5 w-2.5" />MongoDB</span>
          </div>

          <div className="c3d-result" aria-live="polite">
            <b>Evidence assembled</b>
            <span>Decision support, not a fraud verdict.</span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-medium text-muted" aria-live="polite">{steps[step]}</p>
        <button type="button" className="btn-primary px-4 py-2 text-xs" onClick={run}>
          {done ? 'Replay animation' : 'Connect an offer'}
        </button>
      </div>
    </div>
  );
}

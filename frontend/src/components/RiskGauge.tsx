import { AlertTriangle, HelpCircle } from 'lucide-react';
import { scoreColor, titleCase } from '../lib/utils';

const RADIUS = 78;
const CIRCUMFERENCE = Math.PI * RADIUS;

export function RiskGauge({
  score,
  category,
  inconclusive = false,
  confidence,
  compact = false,
}: {
  score: number;
  category: string;
  inconclusive?: boolean;
  confidence?: number;
  compact?: boolean;
}) {
  const safeScore = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0));
  const colour = inconclusive ? '#94a3b8' : scoreColor(safeScore);
  const dash = (safeScore / 100) * CIRCUMFERENCE;

  return (
    <div className={compact ? 'w-full max-w-[260px]' : 'mx-auto w-full max-w-[380px]'}>
      <div className="relative">
        <svg viewBox="0 0 200 118" role="img" aria-label={`Risk score ${safeScore} out of 100, ${titleCase(category)}`} className="w-full overflow-visible">
          <path d="M 22 100 A 78 78 0 0 1 178 100" fill="none" stroke="rgb(var(--c-line))" strokeWidth="14" strokeLinecap="round" />
          <path
            d="M 22 100 A 78 78 0 0 1 178 100"
            fill="none"
            stroke={colour}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${CIRCUMFERENCE}`}
            className="transition-all duration-700"
          />
          <text x="100" y="88" textAnchor="middle" fontSize="42" fontWeight="800" fill="rgb(var(--c-ink))">
            {safeScore}
          </text>
          <text x="100" y="106" textAnchor="middle" fontSize="11" fontWeight="600" fill="rgb(var(--c-muted))">
            RISK SCORE / 100
          </text>
        </svg>
      </div>
      <div className="-mt-1 text-center">
        <p className="text-lg font-bold" style={{ color: colour }}>
          {inconclusive ? 'Inconclusive' : titleCase(category)}
        </p>
        {confidence !== undefined && <p className="mt-1 text-xs text-muted">Assessment confidence: {Math.round(confidence * 100)}%</p>}
        {inconclusive && (
          <p className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-elevated px-2.5 py-1 text-xs text-muted">
            <HelpCircle className="h-3.5 w-3.5" /> Insufficient evidence for a verdict
          </p>
        )}
      </div>
      {!inconclusive && safeScore >= 70 && (
        <p className="mt-3 flex items-center justify-center gap-1.5 text-xs font-semibold text-danger">
          <AlertTriangle className="h-3.5 w-3.5" /> Strong risk signals detected
        </p>
      )}
    </div>
  );
}

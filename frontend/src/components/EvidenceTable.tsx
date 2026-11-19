import { ChevronDown, ExternalLink } from 'lucide-react';
import type { EvidenceIndicator, EvidenceStatus } from '../types';
import { EVIDENCE_GROUPS, cx, formatDate, pct } from '../lib/utils';
import { Badge, EmptyState } from './ui';

export function EvidenceTable({
  indicators = [],
  missingEvidence = [],
  technicalLimitations = [],
  compact = false,
}: {
  indicators?: EvidenceIndicator[];
  missingEvidence?: string[];
  technicalLimitations?: string[];
  compact?: boolean;
}) {
  const grouped = new Map<EvidenceStatus, EvidenceIndicator[]>();
  indicators.forEach((indicator) => {
    const group = grouped.get(indicator.status) ?? [];
    group.push(indicator);
    grouped.set(indicator.status, group);
  });

  const groups = EVIDENCE_GROUPS.map((group) => ({
    ...group,
    items: grouped.get(group.status) ?? [],
  }));

  const extraGroups = [
    {
      label: 'Missing evidence',
      description: 'Required information was not available',
      dot: '#94a3b8',
      items: missingEvidence.map((text) => ({
        name: text,
        status: 'missing' as const,
        severity: 0,
        description: 'Not observed or not supplied for this investigation.',
        source: 'Evidence collector',
        observed_at: '',
        confidence: 0,
      })),
    },
    {
      label: 'Technical limitations',
      description: 'Checks that could not be completed',
      dot: '#64748b',
      items: technicalLimitations.map((text) => ({
        name: text,
        status: 'technical_limitation' as const,
        severity: 0,
        description: 'This limitation reduces the completeness of the assessment.',
        source: 'Analysis engine',
        observed_at: '',
        confidence: 0,
      })),
    },
  ];

  const allGroups = [...groups, ...extraGroups].filter((group) => group.items.length > 0);

  if (!allGroups.length) {
    return <EmptyState title="No structured indicators recorded" description="The analysis did not produce evidence entries in this section." />;
  }

  return (
    <div className="space-y-3">
      {allGroups.map((group, index) => (
        <details key={group.label} className="group overflow-hidden rounded-xl border border-line bg-surface" open={index === 0}>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 hover:bg-elevated">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: group.dot }} />
              <div>
                <p className="text-sm font-semibold">{group.label}</p>
                {!compact && <p className="text-xs text-muted">{group.description}</p>}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone="neutral">{group.items.length}</Badge>
              <ChevronDown className="h-4 w-4 text-muted transition group-open:rotate-180" />
            </div>
          </summary>
          <div className="overflow-x-auto border-t border-line">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-elevated text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Indicator</th>
                  <th className="px-3 py-2.5 font-semibold">Severity</th>
                  <th className="px-3 py-2.5 font-semibold">Confidence</th>
                  <th className="px-3 py-2.5 font-semibold">Source / observed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {group.items.map((item, itemIndex) => (
                  <tr key={`${item.name}-${itemIndex}`} className="align-top hover:bg-elevated/50">
                    <td className="max-w-md px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold">{item.name}</p>
                        {'independently_verified' in item && item.independently_verified && <Badge tone="safe">Verified</Badge>}
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-muted">{item.description}</p>
                      {'reference_url' in item && item.reference_url && (
                        <a href={item.reference_url} target="_blank" rel="noreferrer" className="link mt-1.5 inline-flex items-center gap-1 text-xs">
                          Reference <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-14 overflow-hidden rounded-full bg-elevated">
                          <div className="h-full rounded-full bg-warn" style={{ width: pct(item.severity) }} />
                        </div>
                        <span className="text-xs tabular-nums text-muted">{pct(item.severity)}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs tabular-nums text-muted">{pct(item.confidence)}</td>
                    <td className="px-3 py-3 text-xs text-muted">
                      <p>{item.source}</p>
                      <p>{formatDate(item.observed_at)}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </div>
  );
}

export function evidenceTone(status: EvidenceStatus) {
  return cx(status === 'confirmed_malicious' && 'text-danger');
}

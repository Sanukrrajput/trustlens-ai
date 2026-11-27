import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Download, ShieldAlert, Sparkles } from 'lucide-react';
import { EvidenceTable } from '../components/EvidenceTable';
import { RiskGauge } from '../components/RiskGauge';
import { Badge, Card, Field, SectionHeading } from '../components/ui';
import { scanOfferLocally } from '../lib/localScan';
import { titleCase } from '../lib/utils';
import type { AnalysisResult, OfferCategory } from '../types';

function downloadResult(result: AnalysisResult) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = `trustlens-quick-scan-${result.id}.json`;
  link.click();
  URL.revokeObjectURL(href);
}

export function PublicScanPage() {
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [category, setCategory] = useState<OfferCategory>('other');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim().length < 20 && !url.trim()) {
      setError('Paste at least 20 characters of offer text, or provide a source URL.');
      setResult(null);
      return;
    }
    setError('');
    setResult(scanOfferLocally({ text, url, companyName, category }));
  };

  const riskTone = result
    ? result.risk.score >= 70
      ? 'danger'
      : result.risk.score >= 45
        ? 'warn'
        : 'safe'
    : 'neutral';

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8 lg:py-16">
      <SectionHeading
        eyebrow="Public quick scan"
        title="Check an offer before you act"
        description="A privacy-first, browser-only check for offers, giveaways, scholarship messages, promotions and recruitment adverts. The text and URL never leave this device."
        action={<Badge tone="brand" dot>Rule-based · no sign-in</Badge>}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-6">
          <Card title="What do you want to verify?" subtitle="Paste the full message and, if you have one, the link it points to.">
            <form onSubmit={submit} noValidate className="space-y-5">
              {error && (
                <p role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>
              )}

              <Field
                label="Offer or message text"
                htmlFor="public-scan-text"
                hint="At least 20 characters. Remove passwords, OTPs and full card numbers before scanning."
                required
              >
                <textarea
                  id="public-scan-text"
                  className="input min-h-[200px] resize-y font-mono text-xs leading-relaxed"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="Paste the offer, advert, giveaway, scholarship or recruitment message here…"
                />
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Source URL" htmlFor="public-scan-url" hint="Optional, but it enables local link checks.">
                  <input
                    id="public-scan-url"
                    className="input font-mono text-xs"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder="https://example.com/offer"
                  />
                </Field>
                <Field label="Claimed company or brand" htmlFor="public-scan-company">
                  <input
                    id="public-scan-company"
                    className="input"
                    value={companyName}
                    onChange={(event) => setCompanyName(event.target.value)}
                    placeholder="Optional"
                  />
                </Field>
              </div>

              <Field label="Offer category" htmlFor="public-scan-category">
                <select
                  id="public-scan-category"
                  className="input"
                  value={category}
                  onChange={(event) => setCategory(event.target.value as OfferCategory)}
                >
                  <option value="other">Other offer</option>
                  <option value="advertisement">Advertisement</option>
                  <option value="giveaway">Giveaway / prize</option>
                  <option value="scholarship">Scholarship</option>
                  <option value="investment">Investment</option>
                  <option value="recruitment">Recruitment</option>
                  <option value="promotion">Promotion / discount</option>
                </select>
              </Field>

              <button type="submit" className="btn-primary px-6 py-3">Run quick scan <ArrowRight className="h-4 w-4" /></button>
            </form>
          </Card>

          <div className="rounded-xl border border-line bg-elevated/50 p-4 text-xs leading-relaxed text-muted">
            <ShieldAlert className="mb-2 h-4 w-4 text-warn" />
            This is a rule-based quick scan, not a guarantee. It does not query registries, threat feeds, DNS records or
            community reports. A signed-in full scan is required for those checks.
          </div>
        </div>

        <Card title="What this scan covers" subtitle="Honest limits, by design.">
          <ul className="space-y-3 text-sm text-muted">
            <li><span className="font-semibold text-ink">Content · 30%</span><br />Text patterns such as advance fees, urgency, gift-card payments and sensitive-data requests.</li>
            <li><span className="font-semibold text-ink">URL syntax · 25%</span><br />Hostname, protocol and lookalike-domain patterns when a link is supplied.</li>
            <li><span className="font-semibold text-ink">Brand consistency · 25%</span><br />Only when a claimed company or sender email is available.</li>
            <li className="opacity-70"><span className="font-semibold">Threat feeds · 10%</span><br />Not available in the public browser scan.</li>
            <li className="opacity-70"><span className="font-semibold">Community signals · 10%</span><br />Not available in the public browser scan.</li>
          </ul>
          <p className="mt-5 border-t border-line pt-4 text-xs text-muted">
            For account-based scanning, persistent reports and the full evidence workflow,{' '}
            <Link className="link" to="/register">create a free account</Link>.
          </p>
        </Card>
      </div>

      {result && (
        <div aria-live="polite" className="mt-8 space-y-6">
          <Card title="Quick-scan result" subtitle="Local rules only — nothing was uploaded.">
            <div className="grid gap-6 md:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] md:items-center">
              <RiskGauge
                score={result.risk.score}
                category={result.risk.category}
                inconclusive={result.risk.inconclusive}
                confidence={result.risk.confidence}
              />
              <div>
                <Badge tone={riskTone}>{titleCase(result.risk.category)} risk</Badge>
                <p className="mt-4 text-sm leading-relaxed text-muted">{result.risk.summary}</p>
                <ul className="mt-4 space-y-2">
                  {result.risk.recommended_actions?.map((action) => (
                    <li key={action} className="flex gap-2 text-sm text-muted">
                      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> {action}
                    </li>
                  ))}
                </ul>
                <button type="button" className="btn-secondary mt-5" onClick={() => downloadResult(result)}>
                  <Download className="h-4 w-4" /> Download evidence JSON
                </button>
              </div>
            </div>
          </Card>

          <Card title="Signals and evidence" subtitle="Every finding carries a source, severity, confidence and limitation.">
            <EvidenceTable
              indicators={result.indicators}
              missingEvidence={result.missing_evidence}
              technicalLimitations={result.technical_limitations}
            />
          </Card>

          <Card title="What was not checked" subtitle="Missing evidence is part of the result, not hidden.">
            <ul className="grid gap-2 text-sm text-muted sm:grid-cols-2">
              {result.risk.unavailable_signals.map((signal) => (
                <li key={signal} className="rounded-lg border border-line bg-elevated/40 px-3 py-2">{signal}</li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}

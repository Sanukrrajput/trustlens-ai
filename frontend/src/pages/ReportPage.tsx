import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  Download,
  ExternalLink,
  FileWarning,
  Globe2,
  HelpCircle,
  History,
  Lightbulb,
  Mail,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import { EvidenceTable } from '../components/EvidenceTable';
import { RiskGauge } from '../components/RiskGauge';
import { Badge, Card, EmptyState, ErrorState, Field, ProgressBar, SectionHeading, Spinner } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { useApi } from '../hooks/useApi';
import { analysisApi, reportsApi } from '../lib/api';
import { downloadBlob, errorText, formatDateTime, pct, titleCase } from '../lib/utils';
import { validateFeedback } from '../lib/validation';
import type { AnalysisResult, CommunityClaimType, UserReportOut } from '../types';

function ValueBlock({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-elevated/40 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</p>
      <div className="mt-1.5 text-sm">{value}</div>
    </div>
  );
}

function TagList({ values }: { values: string[] }) {
  if (!values.length) return <span className="text-xs text-muted">None extracted</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {values.map((value, index) => <span key={`${value}-${index}`} className="chip text-[11px]">{value}</span>)}
    </div>
  );
}

function IntelligenceCard({ title, icon, data }: { title: string; icon: ReactNode; data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {});
  return (
    <Card title={<span className="flex items-center gap-2">{icon}{title}</span>}>
      {entries.length ? (
        <dl className="space-y-2">
          {entries.map(([key, value]) => (
            <div key={key} className="flex flex-col gap-1 border-b border-line/60 pb-2 last:border-0 last:pb-0">
              <dt className="text-xs font-semibold text-muted">{titleCase(key)}</dt>
              <dd className="break-words text-sm">
                {typeof value === 'object' && value !== null ? (
                  <pre className="overflow-x-auto rounded-lg bg-elevated p-2 text-[11px] leading-relaxed">{JSON.stringify(value, null, 2)}</pre>
                ) : String(value)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-muted">No data recorded for this section.</p>
      )}
    </Card>
  );
}

export function ReportPage() {
  const { id = '' } = useParams();
  const location = useLocation();
  const { notify } = useToast();
  const initialResult = (location.state as { result?: AnalysisResult } | null)?.result;
  const { data: result, loading, error, refetch } = useApi<AnalysisResult>(() => analysisApi.get(id), [id], {
    initialData: initialResult,
  });
  const [downloading, setDownloading] = useState(false);
  const [feedback, setFeedback] = useState({ report_type: 'false_positive', details: '', evidence_url: '' });
  const [feedbackErrors, setFeedbackErrors] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [community, setCommunity] = useState({ claim_type: 'missed_fraud' as CommunityClaimType, details: '', evidence_url: '' });
  const [communityErrors, setCommunityErrors] = useState<Record<string, string>>({});
  const [sendingCommunity, setSendingCommunity] = useState(false);
  const [communityReceipt, setCommunityReceipt] = useState<UserReportOut | null>(null);

  if (loading) return <Spinner label="Loading investigation report…" className="min-h-[60vh]" />;
  if (error) return <ErrorState message={error} onRetry={() => void refetch()} />;
  if (!result) return <EmptyState title="Report not found" description="This investigation may have been removed." action={<Link className="btn-secondary" to="/app">Back to dashboard</Link>} />;

  const risk = result.risk;
  const extracted = result.extracted ?? {
    company_names: [], job_titles: [], recruiter_emails: [], phone_numbers: [], urls: [], payment_demands: [], sensitive_data_requests: [], locations: [],
  };

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const blob = await reportsApi.pdf(result.report_id ?? result.id);
      downloadBlob(blob, `trustlens-report-${result.id}.pdf`);
      notify('PDF report downloaded.', 'success');
    } catch (error) {
      notify(errorText(error), 'error');
    } finally {
      setDownloading(false);
    }
  };

  const submitCommunity = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateFeedback(community);
    setCommunityErrors(found);
    if (Object.keys(found).length) return;
    setSendingCommunity(true);
    try {
      const receipt = await reportsApi.community({
        analysis_id: result.id,
        claim_type: community.claim_type,
        details: community.details.trim(),
        evidence_url: community.evidence_url.trim() || undefined,
      });
      setCommunityReceipt(receipt);
      setCommunity({ claim_type: 'missed_fraud', details: '', evidence_url: '' });
      notify(
        receipt.duplicate
          ? 'This report was already recorded; no duplicate was created.'
          : 'Community report submitted for moderation. One report alone never changes an entity risk class.',
        'success',
      );
    } catch (error) {
      notify(errorText(error), 'error');
    } finally {
      setSendingCommunity(false);
    }
  };

  const submitFeedback = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateFeedback(feedback);
    setFeedbackErrors(found);
    if (Object.keys(found).length) return;
    setSending(true);
    try {
      await reportsApi.feedback({
        analysis_id: result.id,
        report_type: feedback.report_type as 'false_positive' | 'missed_fraud' | 'identity_correction' | 'other',
        details: feedback.details.trim(),
        evidence_url: feedback.evidence_url.trim() || undefined,
      });
      setFeedbackSent(true);
      setFeedback({ report_type: 'false_positive', details: '', evidence_url: '' });
      notify('Thank you. Your correction has been submitted for review.', 'success');
    } catch (error) {
      notify(errorText(error), 'error');
    } finally {
      setSending(false);
    }
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link to="/app" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" /> Back to dashboard</Link>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={() => void refetch()}><RefreshCw className="h-4 w-4" /> Refresh</button>
          <button className="btn-primary" onClick={() => void downloadPdf()} disabled={downloading}>
            {downloading ? <Spinner label="" className="min-h-0 p-0" /> : <Download className="h-4 w-4" />} Download PDF
          </button>
        </div>
      </div>

      <SectionHeading
        eyebrow={`Investigation report · ${result.id}`}
        title={titleCase(result.analysis_type) + ' analysis'}
        description={`Created ${formatDateTime(result.created_at)} · Status: ${result.status}`}
        action={<Badge tone={risk.inconclusive ? 'warn' : risk.score >= 70 ? 'danger' : 'safe'} dot>{result.status}</Badge>}
      />

      {result.status === 'pending' && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-brand-500/30 bg-brand-500/10 px-4 py-3 text-sm text-brand-700 dark:text-brand-300">
          <RefreshCw className="h-4 w-4 animate-spin" /> This analysis is still processing. Refresh in a moment to see the completed report.
        </div>
      )}

      {risk.inconclusive && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-warn/40 bg-warn/10 px-4 py-3.5">
          <HelpCircle className="mt-0.5 h-5 w-5 shrink-0 text-warn" />
          <div>
            <p className="text-sm font-bold text-warn">Inconclusive assessment</p>
            <p className="mt-1 text-sm text-muted">
              Available evidence is insufficient for a reliable verdict. Treat missing evidence and technical limitations as unresolved — not as a clean result. Seek independent verification.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <div className="space-y-6">
          <Card title="Risk assessment">
            <RiskGauge score={risk.score} category={risk.category} inconclusive={risk.inconclusive} confidence={risk.confidence} />
            <div className="mt-6 space-y-4 border-t border-line pt-5">
              <div>
                <div className="flex items-center justify-between text-xs text-muted"><span>Assessment confidence</span><span>{pct(risk.confidence)}</span></div>
                <ProgressBar value={risk.confidence * 100} className="mt-1.5" />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs text-muted"><span>Evidence uncertainty</span><span>{pct(risk.uncertainty ?? 1 - risk.confidence)}</span></div>
                <ProgressBar value={(risk.uncertainty ?? 1 - risk.confidence) * 100} tone="warn" className="mt-1.5" />
              </div>
              <div>
                <div className="flex items-center justify-between text-xs text-muted"><span>Data coverage</span><span>{pct(risk.data_coverage)}</span></div>
                <ProgressBar value={risk.data_coverage * 100} tone={risk.data_coverage < 0.4 ? 'warn' : 'brand'} className="mt-1.5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-muted">Signal weights</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {Object.entries(risk.signal_weights ?? {}).map(([name, weight]) => (
                    <span key={name} className="chip text-[11px]">{titleCase(name)} {pct(weight)}</span>
                  ))}
                </div>
                {!!risk.unavailable_signals?.length && (
                  <p className="mt-2 text-[11px] text-warn">
                    Unavailable: {risk.unavailable_signals.map((name) => titleCase(name)).join(', ')}. Missing evidence is never treated as clean.
                  </p>
                )}
              </div>
              <p className="text-[11px] text-muted">Weights version: <span className="font-mono">{risk.weights_version}</span></p>
            </div>
          </Card>

          <Card title="Recommended actions">
            <ul className="space-y-3">
              {(risk.recommended_actions ?? []).length ? (
                risk.recommended_actions!.map((action, index) => (
                  <li key={index} className="flex gap-2.5 text-sm text-muted">
                    <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-warn" /> {action}
                  </li>
                ))
              ) : <li className="text-sm text-muted">No actions were generated.</li>}
            </ul>
          </Card>

          <Card title="Evidence sources" subtitle="Status and timestamps for every checked source">
            {result.evidence_sources?.length ? (
              <ul className="space-y-3">
                {result.evidence_sources.map((source, index) => (
                  <li key={`${source.name}-${index}`} className="rounded-xl border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{titleCase(source.name)}</p>
                      <Badge tone={source.status === 'succeeded' ? 'safe' : 'warn'}>{titleCase(source.status)}</Badge>
                    </div>
                    <p className="mt-1 text-[11px] text-muted">
                      Attempted {formatDateTime(source.attempted_at)} · Observed {formatDateTime(source.observed_at)}
                    </p>
                    {source.detail && <p className="mt-1 text-[11px] text-muted">{source.detail}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No source records were captured for this report.</p>
            )}
            <p className="mt-3 text-[11px] text-muted">
              Attempted ({result.sources_attempted.length}) · Succeeded ({result.sources_succeeded.length})
            </p>
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          <Card title="Assessment summary">
            <p className="text-sm leading-relaxed">{risk.summary}</p>
            {!!risk.evidence_summary?.length && (
              <ul className="mt-4 space-y-2 border-t border-line pt-4">
                {risk.evidence_summary.map((line, index) => (
                  <li key={index} className="flex gap-2 text-sm text-muted"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> {line}</li>
                ))}
              </ul>
            )}
            <p className="mt-4 rounded-xl bg-elevated/60 p-3 text-xs text-muted">
              {risk.inconclusive
                ? 'Always corroborate before taking action.'
                : risk.score >= 70
                  ? 'Strong risk signals were observed. Do not share money or sensitive documents.'
                  : 'A lower score does not guarantee legitimacy. Continue standard due diligence.'}
            </p>
          </Card>

          <Card title="Evidence table" subtitle="Grouped by status with source, severity and confidence">
            <EvidenceTable indicators={result.indicators} missingEvidence={result.missing_evidence} technicalLimitations={result.technical_limitations} />
          </Card>

          <Card title="Extracted entities">
            <div className="grid gap-3 sm:grid-cols-2">
              <ValueBlock label="Company names" value={<TagList values={extracted.company_names} />} />
              <ValueBlock label="Claimed roles" value={<TagList values={extracted.job_titles} />} />
              <ValueBlock label="Salary or reward" value={extracted.salary || 'Not stated'} />
              <ValueBlock label="Claimed contact emails" value={<TagList values={extracted.recruiter_emails} />} />
              <ValueBlock label="Phone numbers" value={<TagList values={extracted.phone_numbers} />} />
              <ValueBlock label="URLs" value={<TagList values={extracted.urls} />} />
              <ValueBlock label="Payment demands" value={<TagList values={extracted.payment_demands} />} />
              <ValueBlock label="Sensitive data requests" value={<TagList values={extracted.sensitive_data_requests} />} />
              <ValueBlock label="Locations" value={<TagList values={extracted.locations} />} />
            </div>
          </Card>

          <Card title="Model predictions" subtitle="Uncalibrated model risk scores are advisory, not fraud probabilities">
            <div className="space-y-4">
              {result.model_predictions.length ? result.model_predictions.map((prediction, index) => (
                <div key={index} className="rounded-xl border border-line p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold">{prediction.model_name} <span className="font-mono text-xs text-muted">v{prediction.model_version}</span></p>
                    <Badge tone={prediction.fraud_probability >= 0.7 ? 'danger' : prediction.fraud_probability >= 0.4 ? 'warn' : 'safe'}>
                      {titleCase(prediction.prediction)} · {pct(prediction.fraud_probability)}
                    </Badge>
                  </div>
                  <p className="mt-2 text-xs text-muted">Model risk score (uncalibrated): {pct(prediction.fraud_probability)} · Model confidence: {pct(prediction.confidence)}</p>
                  {!!prediction.contributing_features?.length && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {prediction.contributing_features.map((feature, featureIndex) => (
                        <span key={featureIndex} className="chip text-[11px]">{String(feature.feature ?? JSON.stringify(feature))}</span>
                      ))}
                    </div>
                  )}
                  {!!prediction.limitations?.length && (
                    <ul className="mt-3 space-y-1 text-xs text-muted">
                      {prediction.limitations.map((limitation, limitationIndex) => (
                        <li key={limitationIndex} className="flex gap-1.5"><AlertCircle className="mt-0.5 h-3 w-3 shrink-0" /> {limitation}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )) : <p className="text-sm text-muted">No model predictions recorded.</p>}
            </div>
          </Card>

          <div className="grid gap-6 md:grid-cols-2">
            <IntelligenceCard title="Domain intelligence" icon={<Globe2 className="h-4 w-4 text-brand-500" />} data={result.domain_intelligence} />
            <IntelligenceCard title="Company intelligence" icon={<Building2 className="h-4 w-4 text-brand-500" />} data={result.company_intelligence} />
            <IntelligenceCard title="Message intelligence" icon={<Mail className="h-4 w-4 text-brand-500" />} data={result.message_intelligence} />
            <IntelligenceCard title="Historical intelligence" icon={<History className="h-4 w-4 text-brand-500" />} data={result.historical_intelligence} />
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <Card title="Missing information / evidence">
              {result.missing_evidence.length ? (
                <ul className="space-y-2">
                  {result.missing_evidence.map((item, index) => (
                    <li key={index} className="flex gap-2 text-sm text-muted"><FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-warn" /> {item}</li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">No missing evidence recorded.</p>}
            </Card>
            <Card title="Technical limitations">
              {result.technical_limitations.length ? (
                <ul className="space-y-2">
                  {result.technical_limitations.map((item, index) => (
                    <li key={index} className="flex gap-2 text-sm text-muted"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted" /> {item}</li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">No technical limitations recorded.</p>}
            </Card>
          </div>

          <Card title="Report a correction" subtitle="Help improve accuracy. Corrections are reviewed by the team.">
            {feedbackSent && (
              <div className="mb-4 flex items-center gap-2 rounded-xl border border-safe/30 bg-safe/10 px-4 py-3 text-sm text-safe">
                <CheckCircle2 className="h-4 w-4" /> Your report was submitted. Thank you.
              </div>
            )}
            <form onSubmit={submitFeedback} noValidate className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Report type" htmlFor="feedback-type">
                  <select id="feedback-type" className="input" value={feedback.report_type} onChange={(event) => setFeedback((current) => ({ ...current, report_type: event.target.value }))}>
                    <option value="false_positive">False positive</option>
                    <option value="missed_fraud">Missed fraud signal</option>
                    <option value="identity_correction">Identity correction</option>
                    <option value="other">Other</option>
                  </select>
                </Field>
                <Field label="Supporting URL (optional)" htmlFor="feedback-url">
                  <input id="feedback-url" className="input" value={feedback.evidence_url} onChange={(event) => setFeedback((current) => ({ ...current, evidence_url: event.target.value }))} placeholder="https://…" />
                </Field>
              </div>
              <Field label="Details" htmlFor="feedback-details" error={feedbackErrors.details} hint="At least 10 characters. Describe what is incorrect and why." required>
                <textarea id="feedback-details" className="input min-h-[110px] resize-y" value={feedback.details} onChange={(event) => setFeedback((current) => ({ ...current, details: event.target.value }))} />
              </Field>
              <button className="btn-secondary" type="submit" disabled={sending}>
                {sending ? <Spinner label="" className="min-h-0 p-0" /> : <><ShieldAlert className="h-4 w-4" /> Submit correction</>}
              </button>
            </form>
          </Card>

          <Card
            title="Report a community concern"
            subtitle="Separate from corrections. Moderators review claims; independent corroboration is required before any community signal is used."
          >
            {communityReceipt && (
              <div className="mb-4 rounded-xl border border-line bg-elevated/40 p-3 text-sm text-muted">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <CheckCircle2 className="h-4 w-4 text-safe" />
                  {communityReceipt.duplicate ? 'Matching report already on file' : 'Community report received'}
                </p>
                <p className="mt-1">
                  Moderation state: <span className="font-mono">{communityReceipt.moderation_state}</span>
                  {' · '}Duplicate group: <span className="font-mono">{communityReceipt.duplicate_group_key.slice(0, 12)}…</span>
                </p>
                <p className="mt-1">A single report cannot change an entity's risk classification.</p>
              </div>
            )}
            <form onSubmit={submitCommunity} noValidate className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Claim type" htmlFor="community-claim">
                  <select
                    id="community-claim"
                    className="input"
                    value={community.claim_type}
                    onChange={(event) => setCommunity((current) => ({ ...current, claim_type: event.target.value as CommunityClaimType }))}
                  >
                    <option value="missed_fraud">Missed fraud signal</option>
                    <option value="impersonation">Brand impersonation</option>
                    <option value="unauthorized_campaign">Unauthorised campaign</option>
                    <option value="other">Other concern</option>
                  </select>
                </Field>
                <Field label="Supporting URL (optional)" htmlFor="community-url">
                  <input
                    id="community-url"
                    className="input"
                    value={community.evidence_url}
                    onChange={(event) => setCommunity((current) => ({ ...current, evidence_url: event.target.value }))}
                    placeholder="https://…"
                  />
                </Field>
              </div>
              <Field
                label="What did you observe?"
                htmlFor="community-details"
                error={communityErrors.details}
                hint="At least 10 characters. Describe the claim, not a correction to this report."
                required
              >
                <textarea
                  id="community-details"
                  className="input min-h-[110px] resize-y"
                  value={community.details}
                  onChange={(event) => setCommunity((current) => ({ ...current, details: event.target.value }))}
                />
              </Field>
              <button className="btn-secondary" type="submit" disabled={sendingCommunity}>
                {sendingCommunity ? <Spinner label="" className="min-h-0 p-0" /> : <><ShieldAlert className="h-4 w-4" /> Submit community report</>}
              </button>
            </form>
          </Card>

          {result.report_id && (
            <p className="flex items-center gap-2 text-xs text-muted"><Sparkles className="h-3.5 w-3.5" /> Linked report: <span className="font-mono">{result.report_id}</span> <ExternalLink className="h-3 w-3" /></p>
          )}
        </div>
      </div>
    </div>
  );
}

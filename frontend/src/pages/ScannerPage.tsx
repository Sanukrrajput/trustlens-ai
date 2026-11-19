import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileUp,
  Link2,
  Loader2,
  Mail,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TextQuote,
} from 'lucide-react';
import { FileDropzone } from '../components/FileDropzone';
import { Card, Field, SectionHeading, Tabs } from '../components/ui';
import { useToast } from '../context/ToastContext';
import { analysisApi, resolveAnalysis } from '../lib/api';
import { errorText } from '../lib/utils';
import { validateJob, validateMessage, validateUrl } from '../lib/validation';

type ScannerTab = 'job' | 'url' | 'message' | 'document';

const progressSteps = [
  'Preparing submission…',
  'Extracting entities and claims…',
  'Checking corroborating signals…',
  'Assembling explainable evidence…',
  'Finalising assessment…',
];

function clientRequestId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `web-${Date.now()}`;
  }
}

export function ScannerPage() {
  const navigate = useNavigate();
  const { notify } = useToast();
  const [tab, setTab] = useState<ScannerTab>('job');
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    text: '',
    company_name: '',
    job_title: '',
    recruiter_email: '',
    source_url: '',
    channel: 'email' as 'email' | 'sms' | 'whatsapp' | 'unknown',
    sender: '',
    url: '',
  });
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));

  const startProgress = () => {
    setProgress(4);
    timer.current = window.setInterval(() => {
      setProgress((current) => Math.min(88, current + Math.random() * 9 + 3));
    }, 420);
  };

  const stopProgress = () => {
    window.clearInterval(timer.current);
    timer.current = undefined;
    setProgress(100);
    window.setTimeout(() => setProgress(0), 500);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setServerError('');
    const found =
      tab === 'job'
        ? validateJob(form)
        : tab === 'message'
          ? validateMessage(form)
          : tab === 'url'
            ? validateUrl(form)
            : file
              ? {}
              : { file: 'Choose a document to analyse.' };
    setErrors(found);
    if (Object.keys(found).length) return;

    setSubmitting(true);
    startProgress();
    try {
      const request = { consent_external_lookups: consent, client_request_id: clientRequestId() };
      let initial;
      if (tab === 'job') {
        initial = await analysisApi.submitJob({
          ...request,
          text: form.text.trim(),
          company_name: form.company_name.trim() || undefined,
          job_title: form.job_title.trim() || undefined,
          recruiter_email: form.recruiter_email.trim() || undefined,
          source_url: form.source_url.trim() || undefined,
        });
      } else if (tab === 'message') {
        initial = await analysisApi.submitMessage({
          ...request,
          text: form.text.trim(),
          channel: form.channel,
          sender: form.sender.trim() || undefined,
        });
      } else if (tab === 'url') {
        initial = await analysisApi.submitUrl({ ...request, url: form.url.trim() });
      } else {
        initial = await analysisApi.submitDocument(file!, consent);
      }
      const resolved = await resolveAnalysis(initial);
      notify('Analysis complete. Opening your report…', 'success');
      navigate(`/app/reports/${resolved.id}`, { replace: true, state: { result: resolved.result } });
    } catch (error) {
      setServerError(errorText(error));
      notify(errorText(error), 'error');
    } finally {
      stopProgress();
      setSubmitting(false);
    }
  };

  const activeStep = progressSteps[Math.min(progressSteps.length - 1, Math.floor((progress / 100) * progressSteps.length))];

  return (
    <div>
      <SectionHeading
        eyebrow="Analysis engine"
        title="Start a new investigation"
        description="Choose an input type. Results explain what was observed, what could not be verified, and how confident the assessment is."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card pad={false}>
          <div className="border-b border-line p-4 sm:p-5">
            <Tabs<ScannerTab>
              value={tab}
              onChange={(next) => {
                setTab(next);
                setErrors({});
                setServerError('');
              }}
              items={[
                { key: 'job', label: 'Job text', icon: <TextQuote className="h-4 w-4" /> },
                { key: 'url', label: 'URL', icon: <Link2 className="h-4 w-4" /> },
                { key: 'message', label: 'Recruiter message', icon: <Mail className="h-4 w-4" /> },
                { key: 'document', label: 'Document', icon: <FileUp className="h-4 w-4" /> },
              ]}
            />
          </div>

          <form onSubmit={submit} noValidate className="space-y-5 p-4 sm:p-6">
            {serverError && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{serverError}</div>}

            {tab === 'job' && (
              <>
                <Field label="Job description" htmlFor="job-text" error={errors.text} hint="Paste the full post — at least 20 characters. Never include real passwords or financial credentials." required>
                  <textarea id="job-text" className="input min-h-[220px] resize-y font-mono text-xs leading-relaxed" value={form.text} onChange={(event) => set('text', event.target.value)} placeholder="Paste the job advertisement here…" />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Claimed company" htmlFor="job-company">
                    <input id="job-company" className="input" value={form.company_name} onChange={(event) => set('company_name', event.target.value)} placeholder="Optional" />
                  </Field>
                  <Field label="Job title" htmlFor="job-title">
                    <input id="job-title" className="input" value={form.job_title} onChange={(event) => set('job_title', event.target.value)} placeholder="Optional" />
                  </Field>
                  <Field label="Recruiter email" htmlFor="job-email" error={errors.recruiter_email}>
                    <input id="job-email" type="email" className="input" value={form.recruiter_email} onChange={(event) => set('recruiter_email', event.target.value)} placeholder="Optional" />
                  </Field>
                  <Field label="Source URL" htmlFor="job-source" error={errors.source_url}>
                    <input id="job-source" className="input" value={form.source_url} onChange={(event) => set('source_url', event.target.value)} placeholder="https://… (optional)" />
                  </Field>
                </div>
              </>
            )}

            {tab === 'url' && (
              <Field label="URL to analyse" htmlFor="scan-url" error={errors.url} hint="Public job posting or employer page. Include the full https:// address." required>
                <input id="scan-url" className="input font-mono text-xs" value={form.url} onChange={(event) => set('url', event.target.value)} placeholder="https://example.com/careers/role" />
              </Field>
            )}

            {tab === 'message' && (
              <>
                <Field label="Message text" htmlFor="message-text" error={errors.text} hint="At least 5 characters. Remove unrelated personal data where possible." required>
                  <textarea id="message-text" className="input min-h-[200px] resize-y font-mono text-xs leading-relaxed" value={form.text} onChange={(event) => set('text', event.target.value)} placeholder="Paste the recruiter message here…" />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Channel" htmlFor="message-channel">
                    <select id="message-channel" className="input" value={form.channel} onChange={(event) => set('channel', event.target.value as typeof form.channel)}>
                      <option value="email">Email</option>
                      <option value="sms">SMS</option>
                      <option value="whatsapp">WhatsApp</option>
                      <option value="unknown">Unknown</option>
                    </select>
                  </Field>
                  <Field label="Sender" htmlFor="message-sender" error={errors.sender}>
                    <input id="message-sender" className="input" value={form.sender} onChange={(event) => set('sender', event.target.value)} placeholder="Email, phone or handle (optional)" />
                  </Field>
                </div>
              </>
            )}

            {tab === 'document' && (
              <>
                <Field label="Document" error={errors.file} hint="PDF, DOC, DOCX, TXT or images up to 20 MB. Text is extracted automatically." required>
                  <FileDropzone onFile={(selected) => { setFile(selected); setErrors((current) => ({ ...current, file: '' })); }} selected={file} error={errors.file} />
                </Field>
              </>
            )}

            <label className="flex items-start gap-3 rounded-xl border border-line bg-elevated/50 p-4 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-line accent-brand-600"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span>
                <span className="font-semibold">Allow external lookups for this analysis</span>
                <span className="mt-1 block text-xs text-muted">
                  Optional. When enabled, public domain and company sources may be queried and recorded in the report. Local-only analysis works without it.
                </span>
              </span>
            </label>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
              <p className="flex items-center gap-2 text-xs text-muted"><ShieldCheck className="h-4 w-4 text-safe" /> Evidence and limitations are always retained.</p>
              <button type="submit" className="btn-primary px-6" disabled={submitting}>
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <><ScanSearch className="h-4 w-4" /> Run analysis</>}
              </button>
            </div>
          </form>
        </Card>

        <div className="space-y-5">
          <Card title="What you'll receive">
            <ul className="space-y-3 text-sm text-muted">
              {['Weighted risk score with explainable evidence', 'Extracted entities and payment demands', 'Domain, company, message and historical sections', 'Missing evidence and technical limitations', 'Recommended actions you can act on'].map((item) => (
                <li key={item} className="flex gap-2"><Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" /> {item}</li>
              ))}
            </ul>
          </Card>
          <Card title="Privacy notes">
            <p className="text-sm leading-relaxed text-muted">
              Inputs are used to produce your investigation and are retained according to your account settings. Never submit passwords, OTPs or full financial credentials for analysis.
            </p>
          </Card>
        </div>
      </div>

      {submitting && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/60 px-4 backdrop-blur-sm" role="status" aria-live="polite">
          <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-7 shadow-card">
            <div className="mb-5 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500"><ScanSearch className="h-5 w-5" /></div>
              <div>
                <p className="font-bold">Analysing submission</p>
                <p className="text-xs text-muted">This usually takes a few seconds</p>
              </div>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-elevated">
              <div className="h-full rounded-full bg-gradient-to-r from-brand-600 to-cyan-400 transition-all duration-300" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-3 text-sm text-muted">{activeStep}</p>
            <p className="mt-1 text-xs text-muted">{Math.round(progress)}% complete</p>
          </div>
        </div>
      )}
    </div>
  );
}

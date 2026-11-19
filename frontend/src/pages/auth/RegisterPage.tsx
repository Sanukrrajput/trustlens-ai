import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Field } from '../../components/ui';
import { errorText } from '../../lib/utils';
import { validateRegister } from '../../lib/validation';
import { AuthShell } from './AuthShell';

export function RegisterPage() {
  const { register } = useAuth();
  const [form, setForm] = useState({
    email: '',
    password: '',
    full_name: '',
    organisation: '',
    consent_privacy: false,
    consent_terms: false,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');
  const [created, setCreated] = useState(false);

  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateRegister(form);
    setErrors(found);
    setServerError('');
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      await register(form);
      setCreated(true);
    } catch (error) {
      setServerError(errorText(error));
    } finally {
      setSubmitting(false);
    }
  };

  if (created) {
    return (
      <AuthShell title="Account created" subtitle="One more step to secure your workspace." footer={<Link className="link" to="/login">Go to sign in</Link>}>
        <div className="card-pad">
          <CheckCircle2 className="mb-4 h-10 w-10 text-safe" />
          <h2 className="text-lg font-bold">Verify your email address</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            We sent a verification link to <span className="font-semibold text-ink">{form.email}</span>. Open it to activate your account. If it does not arrive, check your spam folder.
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start verifying opportunities with evidence, not guesswork."
      footer={<>Already have an account? <Link className="link" to="/login">Sign in</Link></>}
    >
      <form onSubmit={submit} noValidate className="space-y-4">
        {serverError && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{serverError}</div>}
        <Field label="Full name" htmlFor="register-name" error={errors.full_name} required>
          <input id="register-name" className="input" autoComplete="name" value={form.full_name} onChange={(event) => set('full_name', event.target.value)} placeholder="Asha Sharma" />
        </Field>
        <Field label="Email address" htmlFor="register-email" error={errors.email} required>
          <input id="register-email" type="email" className="input" autoComplete="email" value={form.email} onChange={(event) => set('email', event.target.value)} placeholder="you@example.com" />
        </Field>
        <Field label="Organisation (optional)" htmlFor="register-org">
          <input id="register-org" className="input" value={form.organisation} onChange={(event) => set('organisation', event.target.value)} placeholder="University, team or company" />
        </Field>
        <Field
          label="Password"
          htmlFor="register-password"
          error={errors.password}
          hint="At least 10 characters with uppercase, lowercase and a number."
          required
        >
          <input id="register-password" type="password" className="input" autoComplete="new-password" value={form.password} onChange={(event) => set('password', event.target.value)} placeholder="Create a strong password" />
        </Field>
        <div className="space-y-2">
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 rounded border-line accent-brand-600" checked={form.consent_privacy} onChange={(event) => set('consent_privacy', event.target.checked)} />
            <span>I have read and accept the <Link to="/privacy" className="link">Privacy Policy</Link>.</span>
          </label>
          {errors.consent_privacy && <p role="alert" className="pl-7 text-xs text-danger">{errors.consent_privacy}</p>}
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 rounded border-line accent-brand-600" checked={form.consent_terms} onChange={(event) => set('consent_terms', event.target.checked)} />
            <span>I have read and accept the <Link to="/terms" className="link">Terms of Service</Link>.</span>
          </label>
          {errors.consent_terms && <p role="alert" className="pl-7 text-xs text-danger">{errors.consent_terms}</p>}
        </div>
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Create account <ArrowRight className="h-4 w-4" /></>}
        </button>
      </form>
    </AuthShell>
  );
}

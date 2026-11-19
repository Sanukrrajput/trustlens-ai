import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';
import { Field } from '../../components/ui';
import { authApi } from '../../lib/api';
import { errorText } from '../../lib/utils';
import { validateEmail } from '../../lib/validation';
import { AuthShell } from './AuthShell';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [serverError, setServerError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const validation = validateEmail(email);
    setError(validation ?? '');
    setServerError('');
    if (validation) return;
    setSubmitting(true);
    try {
      await authApi.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setServerError(errorText(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title="Reset your password" subtitle="We will email you a secure reset link." footer={<Link className="link" to="/login">Back to sign in</Link>}>
      {sent ? (
        <div className="card-pad text-center">
          <CheckCircle2 className="mx-auto mb-4 h-10 w-10 text-safe" />
          <p className="font-semibold">Check your inbox</p>
          <p className="mt-2 text-sm text-muted">If an account exists for {email}, a reset link is on its way.</p>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-5">
          {serverError && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{serverError}</div>}
          <Field label="Email address" htmlFor="forgot-email" error={error} required>
            <input id="forgot-email" type="email" className="input" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
          </Field>
          <button className="btn-primary w-full" type="submit" disabled={submitting}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Send reset link <ArrowRight className="h-4 w-4" /></>}
          </button>
        </form>
      )}
    </AuthShell>
  );
}

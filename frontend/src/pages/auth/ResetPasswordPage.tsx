import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';
import { Field } from '../../components/ui';
import { authApi } from '../../lib/api';
import { errorText } from '../../lib/utils';
import { validatePassword } from '../../lib/validation';
import { AuthShell } from './AuthShell';

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found: Record<string, string> = {};
    const passwordError = validatePassword(password);
    if (passwordError) found.password = passwordError;
    if (confirm !== password) found.confirm = 'Passwords do not match.';
    if (!token) found.token = 'Reset link is invalid or expired.';
    setErrors(found);
    setServerError('');
    if (Object.keys(found).length) return;
    setSubmitting(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      setTimeout(() => navigate('/login', { replace: true }), 1800);
    } catch (error) {
      setServerError(errorText(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title="Choose a new password" subtitle="Use a strong, unique password." footer={<Link className="link" to="/login">Back to sign in</Link>}>
      {done ? (
        <div className="card-pad text-center">
          <CheckCircle2 className="mx-auto mb-4 h-10 w-10 text-safe" />
          <p className="font-semibold">Password updated</p>
          <p className="mt-2 text-sm text-muted">Redirecting you to sign in…</p>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="space-y-5">
          {serverError && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{serverError}</div>}
          {errors.token && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{errors.token}</div>}
          <Field label="New password" htmlFor="reset-password" error={errors.password} required>
            <input id="reset-password" type="password" className="input" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </Field>
          <Field label="Confirm new password" htmlFor="reset-confirm" error={errors.confirm} required>
            <input id="reset-confirm" type="password" className="input" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} />
          </Field>
          <button className="btn-primary w-full" type="submit" disabled={submitting}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Update password <ArrowRight className="h-4 w-4" /></>}
          </button>
        </form>
      )}
    </AuthShell>
  );
}

import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Loader2, ShieldCheck, UserRound } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Field } from '../../components/ui';
import { Turnstile } from '../../components/Turnstile';
import {
  authApi,
  clearRememberedSignin,
  getDeviceId,
  getRememberedSignin,
  rotateDeviceId,
  saveRememberedSignin,
} from '../../lib/api';
import { cx, errorText, relativeTime } from '../../lib/utils';
import { validateLogin } from '../../lib/validation';
import type { LoginMode, LoginSecurity } from '../../types';
import { AuthShell } from './AuthShell';

export function LoginPage() {
  const { login, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const initialRemembered = getRememberedSignin();
  const [mode, setMode] = useState<LoginMode>(initialRemembered?.mode ?? 'user');
  const [email, setEmail] = useState(initialRemembered?.email ?? '');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');
  const [remember, setRemember] = useState(!!initialRemembered);
  const [remembered, setRemembered] = useState(initialRemembered);
  const [security, setSecurity] = useState<LoginSecurity | null>(null);
  const [turnstileToken, setTurnstileToken] = useState('');
  const [widgetError, setWidgetError] = useState('');

  useEffect(() => {
    let active = true;
    authApi.securityConfig()
      .then((config) => { if (active) setSecurity(config); })
      .catch(() => {
        if (active) {
          setSecurity({
            enabled: false,
            status: 'not_configured',
            provider: 'cloudflare_turnstile',
            note: 'Verification status could not be loaded; sign-in will be retried without a challenge.',
          });
        }
      });
    return () => { active = false; };
  }, []);

  const selectMode = (next: LoginMode) => {
    setMode(next);
    setServerError('');
    setWidgetError('');
    setTurnstileToken('');
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateLogin({ email, password });
    setErrors(found);
    setServerError('');
    if (Object.keys(found).length) return;
    if (security?.enabled && !turnstileToken) {
      setServerError('Complete the security verification before signing in.');
      return;
    }
    setSubmitting(true);
    try {
      const { user: signedInUser, session } = await login(email.trim(), password, {
        access_mode: mode,
        device_id: getDeviceId(),
        remember_device: remember,
        turnstile_token: security?.enabled ? turnstileToken : undefined,
      });

      // The API already rejects a mismatched access_mode. This client-side check
      // stops navigation (and clears any tokens) if an older/unpatched API ignores it.
      const adminRole = signedInUser.role === 'admin' || signedInUser.role === 'owner';
      if ((mode === 'admin') !== adminRole) {
        await logout();
        setServerError(
          mode === 'admin'
            ? 'This account does not have administrator access. Use User login instead.'
            : 'This is an administrator account. Use Admin login instead.',
        );
        return;
      }

      if (remember) {
        saveRememberedSignin({
          email: email.trim(),
          mode,
          device_id: session.device_id,
          previous_signin: session.previous_signin,
          saved_at: new Date().toISOString(),
        });
        setRemembered(getRememberedSignin());
      } else {
        clearRememberedSignin();
        rotateDeviceId();
        setRemembered(null);
      }
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? (mode === 'admin' ? '/app/admin' : '/app'), { replace: true });
    } catch (error) {
      setServerError(errorText(error));
      setTurnstileToken('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Welcome back"
      subtitle={
        mode === 'admin'
          ? 'Administrator sign-in — manage users, models, plans and platform health.'
          : 'Sign in to continue your investigations.'
      }
      footer={<>New to HireShield? <Link className="link" to="/register">Create an account</Link></>}
    >
      <form onSubmit={submit} noValidate className="space-y-5">
        <div role="group" aria-label="Sign-in area" className="grid grid-cols-2 gap-2 rounded-xl border border-line bg-elevated p-1">
          <button
            type="button"
            aria-pressed={mode === 'user'}
            onClick={() => selectMode('user')}
            className={cx(
              'flex items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-left transition',
              mode === 'user' ? 'bg-brand-600 text-white shadow-sm' : 'text-muted hover:bg-surface hover:text-ink',
            )}
          >
            <UserRound className="h-4 w-4 shrink-0" />
            <span>
              <span className="block text-sm font-semibold">User login</span>
              <span className={cx('block text-[11px]', mode === 'user' ? 'text-white/80' : 'text-muted')}>Your workspace</span>
            </span>
          </button>
          <button
            type="button"
            aria-pressed={mode === 'admin'}
            onClick={() => selectMode('admin')}
            className={cx(
              'flex items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-left transition',
              mode === 'admin' ? 'bg-brand-600 text-white shadow-sm' : 'text-muted hover:bg-surface hover:text-ink',
            )}
          >
            <ShieldCheck className="h-4 w-4 shrink-0" />
            <span>
              <span className="block text-sm font-semibold">Admin login</span>
              <span className={cx('block text-[11px]', mode === 'admin' ? 'text-white/80' : 'text-muted')}>Admin console</span>
            </span>
          </button>
        </div>

        {serverError && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{serverError}</div>}
        {remembered?.previous_signin && (
          <div className="rounded-xl border border-brand-500/20 bg-brand-500/5 px-4 py-3 text-xs leading-relaxed text-muted">
            <span className="inline-flex items-center gap-1.5 font-semibold text-brand-700 dark:text-brand-300">
              <ShieldCheck className="h-3.5 w-3.5" /> Previous sign-in
            </span>
            <span className="mt-1 block">
              {remembered.previous_signin.device} · {relativeTime(remembered.previous_signin.at)}
              {remembered.previous_signin.ip_masked ? ` · ${remembered.previous_signin.ip_masked}` : ''}
              {remembered.previous_signin.country ? ` · ${remembered.previous_signin.country}` : ''}
            </span>
            <span className="mt-0.5 block">Only continue if this was you.</span>
          </div>
        )}
        <Field label="Email address" htmlFor="login-email" error={errors.email} required>
          <input id="login-email" type="email" autoComplete="email" className="input" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
        </Field>
        <div>
          <Field label="Password" htmlFor="login-password" error={errors.password} required>
            <input id="login-password" type="password" autoComplete="current-password" className="input" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Your password" />
          </Field>
          <Link to="/forgot-password" className="link mt-2 inline-block text-xs">Forgot password?</Link>
        </div>
        <label className="flex items-start gap-2.5 text-xs text-muted">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 accent-brand-600"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
          />
          <span>Remember this sign-in on this device. Your email and last sign-in details stay local; a device hash is stored on the server.</span>
        </label>
        {security?.enabled && security.site_key && (
          <div className="rounded-xl border border-line bg-elevated p-3">
            <Turnstile
              siteKey={security.site_key}
              onToken={setTurnstileToken}
              onError={(message) => { setWidgetError(message); setTurnstileToken(''); }}
            />
            {widgetError && <p role="alert" className="mt-2 text-xs text-danger">{widgetError}</p>}
          </div>
        )}
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>{mode === 'admin' ? 'Admin sign in' : 'Sign in'} <ArrowRight className="h-4 w-4" /></>}
        </button>
        <p className="text-center text-[11px] leading-relaxed text-muted">
          Choosing an area only routes your sign-in. Access is granted by your verified account role, never by this selection.
        </p>
      </form>
    </AuthShell>
  );
}

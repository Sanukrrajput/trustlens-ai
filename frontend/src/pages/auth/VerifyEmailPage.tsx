import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { authApi } from '../../lib/api';
import { errorText } from '../../lib/utils';
import { AuthShell } from './AuthShell';

type State = 'pending' | 'success' | 'error';

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [state, setState] = useState<State>(token ? 'pending' : 'error');
  const [message, setMessage] = useState(token ? '' : 'This verification link is missing its token. Request a new link from the sign-in page.');
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    authApi
      .verifyEmail(token)
      .then((response) => {
        setState('success');
        setMessage(response?.message ?? 'Your email address has been verified.');
      })
      .catch((error) => {
        setState('error');
        setMessage(errorText(error));
      });
  }, [token]);

  return (
    <AuthShell title="Email verification" subtitle="Confirming your address." footer={<Link className="link" to="/login">Back to sign in</Link>}>
      <div className="card-pad flex flex-col items-center text-center">
        {state === 'pending' && <Loader2 className="mb-4 h-10 w-10 animate-spin text-brand-500" />}
        {state === 'success' && <CheckCircle2 className="mb-4 h-10 w-10 text-safe" />}
        {state === 'error' && <XCircle className="mb-4 h-10 w-10 text-danger" />}
        <p className="font-semibold">{state === 'pending' ? 'Verifying your email…' : state === 'success' ? 'Verification complete' : 'Verification failed'}</p>
        <p className="mt-2 text-sm text-muted">{message}</p>
      </div>
    </AuthShell>
  );
}

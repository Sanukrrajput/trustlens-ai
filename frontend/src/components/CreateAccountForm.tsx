import { useState, type FormEvent } from 'react';
import { Loader2, UserPlus } from 'lucide-react';
import { adminApi } from '../lib/api';
import { errorText } from '../lib/utils';
import type { AdminUserCreate, User } from '../types';

const ASSIGNABLE_ROLES: Array<{ value: AdminUserCreate['role']; label: string }> = [
  { value: 'user', label: 'User — workspace access' },
  { value: 'student', label: 'Student — workspace access' },
  { value: 'staff', label: 'Staff — limited administration' },
  { value: 'admin', label: 'Admin — full admin console' },
];

export function CreateAccountForm({ onCreated }: { onCreated?: (user: User) => void }) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [organisation, setOrganisation] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<AdminUserCreate['role']>('user');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      const created = await adminApi.createUser({
        full_name: fullName.trim(),
        email: email.trim(),
        organisation: organisation.trim() || undefined,
        password,
        role,
      });
      setSuccess(`Created ${created.role} account for ${created.email}. Share the password securely.`);
      setFullName('');
      setEmail('');
      setOrganisation('');
      setPassword('');
      setRole('user');
      onCreated?.(created);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error && <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</div>}
      {success && <div role="status" className="rounded-xl border border-safe/30 bg-safe/10 px-4 py-3 text-sm text-safe">{success}</div>}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-muted">Full name</span>
          <input className="input" value={fullName} onChange={(event) => setFullName(event.target.value)} minLength={2} maxLength={120} required placeholder="Asha Sharma" />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-muted">Email address</span>
          <input className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required placeholder="asha@example.com" />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-muted">Organisation (optional)</span>
          <input className="input" value={organisation} onChange={(event) => setOrganisation(event.target.value)} maxLength={160} placeholder="Example Ltd" />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-muted">Role</span>
          <select className="input" value={role} onChange={(event) => setRole(event.target.value as AdminUserCreate['role'])}>
            {ASSIGNABLE_ROLES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-xs font-semibold text-muted">Temporary password</span>
          <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={10} maxLength={128} autoComplete="new-password" required placeholder="At least 10 characters" />
        </label>
      </div>
      <p className="text-[11px] leading-relaxed text-muted">
        The signed-in admin&apos;s role limits what can be granted. Owner accounts are intentionally excluded. Account creation is written to the audit log.
      </p>
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><UserPlus className="h-4 w-4" /> Create account</>}
      </button>
    </form>
  );
}

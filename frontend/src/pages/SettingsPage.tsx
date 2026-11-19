import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bell,
  Check,
  CheckCheck,
  Database,
  Download,
  Info,
  LockKeyhole,
  Mail,
  Moon,
  ShieldAlert,
  ShieldCheck,
  Sun,
  Trash2,
  UserRound,
} from 'lucide-react';
import { Badge, Card, EmptyState, ErrorState, SectionHeading, Spinner, Tabs } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useToast } from '../context/ToastContext';
import { useApi } from '../hooks/useApi';
import { authApi, clearRememberedSignin, notificationsApi, rotateDeviceId, unwrapList } from '../lib/api';
import { errorText, formatDateTime, relativeTime, titleCase } from '../lib/utils';
import type { NotificationOut, SigninEvent } from '../types';

type SettingsTab = 'notifications' | 'preferences' | 'privacy' | 'security';
const PREFS_KEY = 'hireshield.local_preferences';

interface LocalPreferences {
  emailDigest: boolean;
  highRiskAlerts: boolean;
  monitoringUpdates: boolean;
  productNews: boolean;
}

function readPrefs(): LocalPreferences {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) return { emailDigest: true, highRiskAlerts: true, monitoringUpdates: true, productNews: false, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { emailDigest: true, highRiskAlerts: true, monitoringUpdates: true, productNews: false };
}

export function SettingsPage() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const { notify } = useToast();
  const [tab, setTab] = useState<SettingsTab>('notifications');
  const [prefs, setPrefs] = useState<LocalPreferences>(readPrefs);
  const { data, loading, error, refetch, setData } = useApi(() => notificationsApi.list().then(unwrapList), []);
  const notifications = data ?? [];
  const signins = useApi(() => authApi.signinActivity(10), []);
  const signinEvents: SigninEvent[] = signins.data ?? [];

  const markRead = async (item: NotificationOut) => {
    if (item.read) return;
    try {
      await notificationsApi.markRead(item.id);
      setData(notifications.map((entry) => (entry.id === item.id ? { ...entry, read: true } : entry)));
    } catch (err) {
      notify(errorText(err), 'error');
    }
  };

  const markAll = async () => {
    const unread = notifications.filter((item) => !item.read);
    try {
      await Promise.all(unread.map((item) => notificationsApi.markRead(item.id)));
      setData(notifications.map((item) => ({ ...item, read: true })));
      notify('All notifications marked as read.', 'success');
    } catch (err) {
      notify(errorText(err), 'error');
    }
  };

  const updatePref = (key: keyof LocalPreferences, value: boolean) => {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
    notify('Preference saved on this device.', 'success');
  };

  return (
    <div>
      <SectionHeading eyebrow="Account" title="Settings & notifications" description="Manage alerts, appearance and data choices for your account." />

      <div className="mb-6 max-w-xl">
        <Tabs<SettingsTab>
          value={tab}
          onChange={setTab}
          items={[
            { key: 'notifications', label: 'Notifications', icon: <Bell className="h-4 w-4" /> },
            { key: 'preferences', label: 'Preferences', icon: <Sun className="h-4 w-4" /> },
            { key: 'privacy', label: 'Privacy & data', icon: <LockKeyhole className="h-4 w-4" /> },
            { key: 'security', label: 'Sign-in security', icon: <ShieldCheck className="h-4 w-4" /> },
          ]}
        />
      </div>

      {tab === 'notifications' && (
        <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
          <Card
            title="Notification inbox"
            subtitle={`${notifications.filter((item) => !item.read).length} unread`}
            action={
              notifications.some((item) => !item.read) ? (
                <button className="btn-ghost text-xs" onClick={() => void markAll()}><CheckCheck className="h-4 w-4" /> Mark all read</button>
              ) : undefined
            }
          >
            {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={() => void refetch()} /> : notifications.length ? (
              <ul className="divide-y divide-line">
                {notifications.map((item) => (
                  <li key={item.id} className={`flex gap-3 py-4 first:pt-0 last:pb-0 ${item.read ? 'opacity-70' : ''}`}>
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.read ? 'bg-line' : 'bg-brand-500'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold">{item.title}</p>
                        <Badge tone={/high|critical|danger/i.test(item.severity) ? 'danger' : 'neutral'}>{titleCase(item.severity)}</Badge>
                      </div>
                      <p className="mt-1 text-sm leading-relaxed text-muted">{item.body}</p>
                      <p className="mt-1.5 text-xs text-muted">{formatDateTime(item.created_at)} · {relativeTime(item.created_at)}</p>
                      {item.analysis_id && <Link className="link mt-1.5 inline-block text-xs" to={`/app/reports/${item.analysis_id}`}>View investigation →</Link>}
                    </div>
                    {!item.read && (
                      <button className="btn-secondary h-fit px-3 py-1.5 text-xs" onClick={() => void markRead(item)}>
                        <Check className="h-3.5 w-3.5" /> Mark read
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={<Bell className="h-5 w-5" />} title="No notifications" description="Monitoring alerts and account updates will appear here." />
            )}
          </Card>

          <Card title="Delivery channels">
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-xl border border-line p-3">
                <span className="flex items-center gap-2"><Mail className="h-4 w-4 text-brand-500" /> Email</span>
                <Badge tone="safe">Enabled</Badge>
              </div>
              <div className="flex items-center justify-between rounded-xl border border-line p-3">
                <span className="flex items-center gap-2"><Bell className="h-4 w-4 text-brand-500" /> In-app</span>
                <Badge tone="safe">Enabled</Badge>
              </div>
            </div>
            <p className="mt-4 text-xs leading-relaxed text-muted">Per-monitor delivery choices are configured in Job Monitoring.</p>
          </Card>
        </div>
      )}

      {tab === 'preferences' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Appearance">
            <p className="mb-4 text-sm text-muted">Choose how HireShield looks on this device.</p>
            <div className="grid grid-cols-2 gap-3">
              {(['light', 'dark'] as const).map((value) => (
                <button
                  key={value}
                  className={`flex items-center justify-center gap-2 rounded-xl border p-4 text-sm font-semibold capitalize ${theme === value ? 'border-brand-500 bg-brand-500/10 text-brand-600 dark:text-brand-300' : 'border-line text-muted hover:bg-elevated'}`}
                  onClick={() => setTheme(value)}
                >
                  {value === 'light' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />} {value}
                </button>
              ))}
            </div>
          </Card>

          <Card title="Notification preferences">
            <p className="mb-4 text-sm text-muted">
              These preferences are saved on this device until a preferences API is available. Server-side delivery is controlled per monitoring task.
            </p>
            <div className="space-y-3">
              {([
                ['emailDigest', 'Daily email digest'],
                ['highRiskAlerts', 'High-risk findings'],
                ['monitoringUpdates', 'Monitoring updates'],
                ['productNews', 'Product news'],
              ] as Array<[keyof LocalPreferences, string]>).map(([key, label]) => (
                <label key={key} className="flex items-center justify-between rounded-xl border border-line p-3 text-sm">
                  <span>{label}</span>
                  <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={prefs[key]} onChange={(event) => updatePref(key, event.target.checked)} />
                </label>
              ))}
            </div>
          </Card>

          <Card title="Account details" className="lg:col-span-2">
            <div className="grid gap-4 sm:grid-cols-2">
              <div><p className="label">Name</p><p className="flex items-center gap-2 text-sm"><UserRound className="h-4 w-4 text-muted" /> {user?.full_name ?? '—'}</p></div>
              <div><p className="label">Email</p><p className="text-sm">{user?.email ?? '—'} {user?.email_verified && <Badge tone="safe">Verified</Badge>}</p></div>
              <div><p className="label">Organisation</p><p className="text-sm">{user?.organisation ?? '—'}</p></div>
              <div><p className="label">Role</p><p className="text-sm capitalize">{user?.role ?? '—'}</p></div>
            </div>
          </Card>
        </div>
      )}

      {tab === 'privacy' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Data export">
            <Database className="mb-3 h-6 w-6 text-brand-500" />
            <p className="text-sm leading-relaxed text-muted">
              A self-service data export endpoint is not available in the current API contract. Until it is enabled, contact your administrator or support channel to request an export of your investigations and account data.
            </p>
            <div className="mt-4 rounded-xl border border-dashed border-line bg-elevated/40 p-4 text-xs text-muted">
              <p className="font-semibold text-ink">Status: unavailable</p>
              <p className="mt-1">No export request was sent — this interface does not invent an endpoint.</p>
            </div>
            <button className="btn-secondary mt-4" disabled><Download className="h-4 w-4" /> Request export (unavailable)</button>
          </Card>

          <Card title="Account deletion">
            <Trash2 className="mb-3 h-6 w-6 text-danger" />
            <p className="text-sm leading-relaxed text-muted">
              Account deletion requires a verified backend workflow with identity confirmation and retention checks. No deletion endpoint is available in the current API contract, so no request can be submitted here.
            </p>
            <div className="mt-4 rounded-xl border border-danger/30 bg-danger/5 p-4 text-xs text-danger">
              <p className="font-semibold">Status: unavailable</p>
              <p className="mt-1">Contact support directly if you need your account removed.</p>
            </div>
            <button className="btn-danger mt-4" disabled><ShieldAlert className="h-4 w-4" /> Delete account (unavailable)</button>
          </Card>

          <Card className="lg:col-span-2" title="Your data in analyses">
            <p className="text-sm leading-relaxed text-muted">
              Investigation inputs, extracted entities and evidence are retained as part of your report history. You control whether external lookups are allowed for each analysis. Review our <Link className="link" to="/privacy">Privacy Policy</Link> for retention principles and your choices.
            </p>
            <p className="mt-3 flex items-center gap-2 text-xs text-muted"><Info className="h-4 w-4 text-brand-500" /> Correction requests can be submitted from any investigation report.</p>
          </Card>
        </div>
      )}

      {tab === 'security' && (
        <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
          <Card title="Recent sign-ins" subtitle="Successful sign-ins to your account, newest first">
            {signins.loading ? <Spinner /> : signins.error ? (
              <ErrorState message={signins.error} onRetry={() => void signins.refetch()} />
            ) : signinEvents.length ? (
              <ul className="divide-y divide-line">
                {signinEvents.map((item) => (
                  <li key={item.id} className="py-4 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold">{item.device}</p>
                      <Badge tone={item.known_device ? 'safe' : 'warn'}>
                        {item.known_device ? 'Recognised device' : 'New device'}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {formatDateTime(item.at)} · {relativeTime(item.at)}
                      {item.ip_masked ? ` · ${item.ip_masked}` : ''}
                      {item.country ? ` · ${item.country}` : ''}
                    </p>
                    <p className="mt-1 text-[11px] text-muted">Verification: {item.verification}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={<ShieldCheck className="h-5 w-5" />} title="No sign-ins recorded" description="Successful sign-ins will appear here with device and verification context." />
            )}
          </Card>

          <Card title="This browser">
            <p className="text-sm leading-relaxed text-muted">
              Remembering a sign-in keeps your email and the last sign-in summary on this device. The server stores only a keyed hash of a random browser identifier, never the identifier itself.
            </p>
            <button
              className="btn-secondary mt-4"
              onClick={() => {
                clearRememberedSignin();
                rotateDeviceId();
                notify('This browser will be treated as a new device at the next sign-in.', 'success');
              }}
            >
              Forget this browser
            </button>
            <p className="mt-3 text-[11px] text-muted">Changing browsers or clearing site data also creates a new device identity.</p>
          </Card>
        </div>
      )}
    </div>
  );
}

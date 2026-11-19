import { useState } from 'react';
import { Check, CreditCard, Info, Loader2, ShieldCheck, Sparkles } from 'lucide-react';
import { Card, Badge, EmptyState, ErrorState, ProgressBar, SectionHeading, SkeletonBlock, Spinner } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { useApi } from '../hooks/useApi';
import { billingApi, systemApi } from '../lib/api';
import { openRazorpayCheckout } from '../lib/razorpay';
import { errorText, formatDate, formatMoney } from '../lib/utils';
import type { CheckoutOut, PlanOut } from '../types';

export function BillingPage() {
  const { notify } = useToast();
  const { user } = useAuth();
  const [interval, setIntervalType] = useState<'monthly' | 'yearly'>('monthly');
  const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null);
  const [checkoutInfo, setCheckoutInfo] = useState<CheckoutOut | null>(null);
  const [payment, setPayment] = useState<{ id: string; orderId: string; mode?: CheckoutOut['mode'] } | null>(null);
  const plansApi = useApi(() => billingApi.plans(), []);
  const subscriptionApi = useApi(() => billingApi.subscription(), []);
  const configApi = useApi(() => systemApi.config(), []);

  const configPlans = Array.isArray(configApi.data?.plans) ? (configApi.data.plans as unknown as PlanOut[]) : [];
  const plans = plansApi.data?.length ? plansApi.data : configPlans;
  const subscription = subscriptionApi.data;
  const usage = subscription ? Math.round((subscription.scans_used / Math.max(1, subscription.scan_limit)) * 100) : 0;

  const checkout = async (planCode: string) => {
    setCheckoutPlan(planCode);
    setCheckoutInfo(null);
    setPayment(null);
    try {
      const response = await billingApi.checkout({
        plan_code: planCode,
        interval,
        provider: 'razorpay',
        success_url: `${window.location.origin}/app/billing?checkout=success`,
        cancel_url: `${window.location.origin}/app/billing?checkout=cancelled`,
      });

      if (response.provider === 'razorpay') {
        if (!response.key_id) throw new Error('Razorpay is not configured on this deployment.');
        setCheckoutInfo(response);
        const result = await openRazorpayCheckout({
          key: response.key_id,
          amount: response.amount,
          currency: response.currency,
          name: response.name || 'HireShield AI',
          description: response.description || `${interval} subscription`,
          order_id: response.checkout_id,
          prefill: { name: user?.full_name, email: user?.email },
          notes: { plan_code: planCode, interval },
        });
        setCheckoutInfo(null);
        setPayment({ id: result.razorpay_payment_id, orderId: result.razorpay_order_id, mode: response.mode });
        notify('Payment submitted. Paid access starts only after the signed webhook is verified.', 'success');
        return;
      }

      if (response.checkout_url) {
        window.location.href = response.checkout_url;
        return;
      }
      setCheckoutInfo(response);
      notify('Checkout session created. Complete payment with your provider.', 'success');
      await subscriptionApi.refetch();
    } catch (error) {
      notify(errorText(error), 'error');
    } finally {
      setCheckoutPlan(null);
    }
  };

  return (
    <div>
      <SectionHeading
        eyebrow="Subscription"
        title="Plans & billing"
        description="Plan catalog and subscription status are loaded live from the billing service."
        action={
          <div className="flex rounded-xl border border-line bg-elevated p-1">
            {(['monthly', 'yearly'] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setIntervalType(value)}
                className={`rounded-lg px-4 py-2 text-sm font-semibold capitalize ${interval === value ? 'bg-surface text-ink shadow-sm' : 'text-muted'}`}
              >
                {value}
              </button>
            ))}
          </div>
        }
      />

      <Card className="mb-6" title="Current subscription">
        {subscriptionApi.loading ? (
          <Spinner />
        ) : subscriptionApi.error ? (
          <ErrorState message={subscriptionApi.error} onRetry={() => void subscriptionApi.refetch()} />
        ) : subscription ? (
          <div className="grid gap-6 md:grid-cols-[1fr_1fr]">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-xl font-bold capitalize">{subscription.plan_code}</p>
                <Badge tone={subscription.status === 'active' ? 'safe' : 'warn'} dot>{subscription.status}</Badge>
              </div>
              <p className="mt-2 text-sm text-muted">
                {subscription.interval} billing · {subscription.provider ?? 'provider not set'}
              </p>
              <p className="mt-1 text-sm text-muted">
                {subscription.cancel_at_period_end ? 'Cancels at period end' : 'Renews automatically'} · {subscription.current_period_end ? formatDate(subscription.current_period_end) : 'No end date'}
              </p>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="text-muted">Scans this period</span>
                <span className="font-semibold tabular-nums">{subscription.scans_used} / {subscription.scan_limit || '∞'}</span>
              </div>
              <ProgressBar value={usage} tone={usage > 85 ? 'danger' : 'brand'} />
              <p className="mt-2 text-xs text-muted">{usage}% of your allowance used</p>
            </div>
          </div>
        ) : (
          <EmptyState title="No active subscription" description="Choose a plan below to get started. Some features may be available without a subscription." />
        )}
      </Card>

      {payment && (
        <Card className="mb-6 border-safe/50" title="Payment submitted">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone="warn" dot>Awaiting webhook</Badge>
            {payment.mode && <Badge tone={payment.mode === 'live' ? 'safe' : 'neutral'}>{payment.mode} mode</Badge>}
          </div>
          <p className="mt-3 text-sm text-muted">Payment ID: <span className="font-mono text-xs text-ink">{payment.id}</span></p>
          <p className="mt-1 text-sm text-muted">Order ID: <span className="font-mono text-xs text-ink">{payment.orderId}</span></p>
          <p className="mt-3 text-xs text-muted">
            This screen does not grant access. The subscription changes only after Razorpay sends a signed webhook that the backend verifies.
          </p>
          <button type="button" className="btn-secondary mt-4" onClick={() => void subscriptionApi.refetch()}>
            Refresh subscription status
          </button>
        </Card>
      )}

      {checkoutInfo && (
        <Card className="mb-6 border-brand-500/50" title="Checkout session created">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted">Provider: <span className="font-semibold text-ink">{checkoutInfo.provider}</span> · Checkout ID: <span className="font-mono text-xs">{checkoutInfo.checkout_id}</span></p>
            {checkoutInfo.mode && <Badge tone={checkoutInfo.mode === 'live' ? 'safe' : 'neutral'}>{checkoutInfo.mode} mode</Badge>}
          </div>
          <p className="mt-2 text-sm text-muted">Amount: <span className="font-semibold text-ink">{formatMoney(checkoutInfo.amount, checkoutInfo.currency)}</span></p>
          {checkoutInfo.key_id && (
            <p className="mt-3 inline-flex items-center gap-2 rounded-lg border border-line bg-elevated px-3 py-2 font-mono text-xs">
              <CreditCard className="h-4 w-4 text-brand-500" /> Razorpay key_id: {checkoutInfo.key_id}
            </p>
          )}
          <p className="mt-3 text-xs text-muted">The checkout window could not be opened automatically. Use the checkout ID with your payment provider integration.</p>
        </Card>
      )}

      {plansApi.loading && !plans?.length && (
        <div className="grid gap-5 lg:grid-cols-3">{[0, 1, 2].map((key) => <SkeletonBlock key={key} className="h-80" />)}</div>
      )}

      {plans?.length ? (
        <div className="grid gap-5 lg:grid-cols-3">
          {plans.map((plan) => (
            <Card key={plan.code} className={`relative flex flex-col ${plan.popular ? 'border-brand-500/60 shadow-glow' : ''}`}>
              {plan.popular && <span className="absolute -top-3 left-6 inline-flex items-center gap-1 rounded-full bg-brand-600 px-3 py-1 text-[11px] font-bold text-white"><Sparkles className="h-3 w-3" /> POPULAR</span>}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-lg font-bold">{plan.name}</p>
                  <p className="mt-1 text-sm text-muted">{plan.description}</p>
                </div>
                {!plan.active && <Badge tone="neutral">Inactive</Badge>}
              </div>
              <p className="mt-5 text-3xl font-extrabold tabular-nums">
                {formatMoney(interval === 'monthly' ? plan.price_monthly_paise : plan.price_yearly_paise, plan.currency)}
                <span className="ml-1 text-sm font-medium text-muted">/ {interval === 'monthly' ? 'month' : 'year'}</span>
              </p>
              <p className="mt-1 text-xs text-muted">{plan.scan_limit.toLocaleString()} scans per billing period</p>
              <ul className="mt-5 flex-1 space-y-2.5">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex gap-2 text-sm text-muted"><Check className="mt-0.5 h-4 w-4 shrink-0 text-safe" /> {feature}</li>
                ))}
              </ul>
              <button
                className={`mt-6 w-full ${plan.popular ? 'btn-primary' : 'btn-secondary'}`}
                disabled={!plan.active || checkoutPlan === plan.code}
                onClick={() => void checkout(plan.code)}
              >
                {checkoutPlan === plan.code ? <Loader2 className="h-4 w-4 animate-spin" /> : <><CreditCard className="h-4 w-4" /> Choose {plan.name}</>}
              </button>
            </Card>
          ))}
        </div>
      ) : !plansApi.loading ? (
        <Card>
          <EmptyState title="Plans unavailable" description={plansApi.error ? `The billing service could not be reached: ${plansApi.error}` : 'No active plans are configured. Please try again later.'} />
        </Card>
      ) : null}

      <div className="mt-6 flex items-start gap-3 rounded-xl border border-line bg-surface p-4 text-xs text-muted">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
        <p>Payments are processed by the configured provider. HireShield does not store card details. Billing configuration is read from the backend so prices stay current.</p>
      </div>
      <p className="mt-4 flex items-center gap-2 text-xs text-muted"><ShieldCheck className="h-4 w-4 text-safe" /> Need a change? Contact your administrator or support channel.</p>
    </div>
  );
}

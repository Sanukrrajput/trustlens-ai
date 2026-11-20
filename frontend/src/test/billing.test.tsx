import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BillingPage } from '../pages/BillingPage';
import { billingApi } from '../lib/api';
import { openRazorpayCheckout } from '../lib/razorpay';

const mocks = vi.hoisted(() => ({
  notify: vi.fn(),
  refetch: vi.fn(),
  useApiIndex: 0,
}));

const plan = {
  code: 'professional',
  name: 'Professional',
  description: 'Advanced investigation.',
  price_monthly_paise: 29900,
  price_yearly_paise: 299000,
  currency: 'INR',
  scan_limit: 500,
  features: ['Detailed reports'],
  active: true,
  popular: false,
};

const subscription = {
  id: 'sub_1',
  user_id: 'user_1',
  plan_code: 'free',
  status: 'active',
  interval: 'monthly',
  provider: null,
  scans_used: 0,
  scan_limit: 10,
  cancel_at_period_end: false,
};

vi.mock('../hooks/useApi', () => ({
  useApi: () => {
    const index = mocks.useApiIndex++;
    return {
      data: index === 0 ? [plan] : index === 1 ? subscription : { integrations: { razorpay: true } },
      loading: false,
      error: null,
      refetch: mocks.refetch,
      setData: vi.fn(),
    };
  },
}));

vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ notify: mocks.notify }),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'buyer@example.com', full_name: 'Buyer Person' } }),
}));

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return {
    ...actual,
    billingApi: {
      plans: vi.fn(),
      subscription: vi.fn(),
      checkout: vi.fn(),
    },
    systemApi: { config: vi.fn() },
  };
});

vi.mock('../lib/razorpay', () => ({
  openRazorpayCheckout: vi.fn(),
}));

describe('Razorpay billing checkout', () => {
  beforeEach(() => {
    mocks.useApiIndex = 0;
    vi.mocked(billingApi.checkout).mockResolvedValue({
      provider: 'razorpay',
      checkout_id: 'order_test_1',
      key_id: 'rzp_test_local',
      checkout_url: null,
      amount: 29900,
      currency: 'INR',
      name: 'TrustLens AI — Professional',
      description: 'Monthly subscription',
      mode: 'test',
    });
    vi.mocked(openRazorpayCheckout).mockResolvedValue({
      razorpay_payment_id: 'pay_test_1',
      razorpay_order_id: 'order_test_1',
      razorpay_signature: 'signature_marker',
    });
  });

  it('opens Razorpay with the order id and does not claim paid access before the webhook', async () => {
    const user = userEvent.setup();
    render(<BillingPage />);

    await user.click(await screen.findByRole('button', { name: /choose professional/i }));

    expect(await screen.findByText('Payment submitted')).toBeInTheDocument();
    expect(billingApi.checkout).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'razorpay',
      plan_code: 'professional',
      interval: 'monthly',
    }));
    expect(openRazorpayCheckout).toHaveBeenCalledWith(expect.objectContaining({
      key: 'rzp_test_local',
      order_id: 'order_test_1',
      amount: 29900,
      currency: 'INR',
      prefill: { name: 'Buyer Person', email: 'buyer@example.com' },
    }));
    expect(screen.getByText(/does not grant access/i)).toBeInTheDocument();
    expect(mocks.notify).toHaveBeenCalledWith(expect.stringMatching(/signed webhook/i), 'success');
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  openRazorpayCheckout,
  type RazorpayCheckoutOptions,
  type RazorpayPaymentResponse,
} from '../lib/razorpay';

type Handler = (response: RazorpayPaymentResponse) => void;

interface CapturedOptions {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  handler: Handler;
  modal?: { ondismiss?: () => void };
}

let captured: CapturedOptions | null = null;
let openCalled = false;

class FakeRazorpay {
  constructor(options: Record<string, unknown>) {
    captured = options as unknown as CapturedOptions;
  }

  open() {
    openCalled = true;
  }
}

function installFake() {
  Object.defineProperty(window, 'Razorpay', { value: FakeRazorpay, configurable: true, writable: true });
}

function baseOptions(): RazorpayCheckoutOptions {
  return {
    key: 'rzp_test_local',
    amount: 29900,
    currency: 'INR',
    name: 'HireShield AI — Professional',
    order_id: 'order_test_1',
  };
}

afterEach(() => {
  Reflect.deleteProperty(window, 'Razorpay');
  captured = null;
  openCalled = false;
});

describe('Razorpay checkout wrapper', () => {
  it('opens checkout with the server-created order and resolves with the payment response', async () => {
    installFake();
    const pending = openRazorpayCheckout(baseOptions());
    await vi.waitFor(() => expect(openCalled).toBe(true));

    expect(captured).toMatchObject({
      key: 'rzp_test_local',
      amount: 29900,
      currency: 'INR',
      order_id: 'order_test_1',
    });

    const response: RazorpayPaymentResponse = {
      razorpay_payment_id: 'pay_test_1',
      razorpay_order_id: 'order_test_1',
      razorpay_signature: 'signature_marker',
    };
    captured?.handler(response);
    await expect(pending).resolves.toEqual(response);
  });

  it('rejects when the modal is dismissed without completing payment', async () => {
    installFake();
    const pending = openRazorpayCheckout(baseOptions());
    await vi.waitFor(() => expect(openCalled).toBe(true));

    captured?.modal?.ondismiss?.();
    await expect(pending).rejects.toThrow(/closed before payment completed/i);
  });
});

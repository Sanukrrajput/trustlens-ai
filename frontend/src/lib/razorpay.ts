/**
 * Thin wrapper around the official Razorpay Checkout script.
 *
 * The payment response is returned to the caller for display only. It is never
 * treated as proof of payment: only the server's signed webhook can activate a
 * subscription.
 */

const SCRIPT_ID = 'hireshield-razorpay-checkout';
const SCRIPT_URL = 'https://checkout.razorpay.com/v1/checkout.js';

export interface RazorpayPaymentResponse {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpayCheckoutOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description?: string;
  order_id: string;
  prefill?: { name?: string; email?: string; contact?: string };
  notes?: Record<string, string>;
  theme?: { color?: string };
}

interface RazorpayInstance {
  open(): void;
}

interface RazorpayConstructor {
  new (options: Record<string, unknown>): RazorpayInstance;
}

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor;
  }
}

function loadCheckoutScript(): Promise<void> {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Razorpay checkout requires a browser.'));
  }
  if (window.Razorpay) return Promise.resolve();

  const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    return new Promise<void>((resolve, reject) => {
      if (existing.dataset.loaded === 'true') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error('Could not load the Razorpay checkout script.')), { once: true });
    });
  }

  return new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.src = SCRIPT_URL;
    script.async = true;
    script.onload = () => {
      script.dataset.loaded = 'true';
      resolve();
    };
    script.onerror = () => {
      script.remove();
      reject(new Error('Could not load the Razorpay checkout script.'));
    };
    document.head.appendChild(script);
  });
}

export async function openRazorpayCheckout(options: RazorpayCheckoutOptions): Promise<RazorpayPaymentResponse> {
  if (!options.key) throw new Error('Razorpay is not configured on this deployment.');
  if (!options.order_id) throw new Error('The checkout order is missing. Please start again.');

  await loadCheckoutScript();
  const RazorpayCheckout = window.Razorpay;
  if (!RazorpayCheckout) throw new Error('Razorpay checkout is unavailable. Please try again.');

  return new Promise<RazorpayPaymentResponse>((resolve, reject) => {
    let settled = false;
    let instance: RazorpayInstance;
    try {
      instance = new RazorpayCheckout({
        ...options,
        handler: (response: RazorpayPaymentResponse) => {
          settled = true;
          resolve(response);
        },
        modal: {
          ondismiss: () => {
            if (!settled) reject(new Error('Checkout was closed before payment completed.'));
          },
        },
      });
      instance.open();
    } catch (error) {
      if (!settled) reject(error instanceof Error ? error : new Error('Could not open Razorpay checkout.'));
    }
  });
}

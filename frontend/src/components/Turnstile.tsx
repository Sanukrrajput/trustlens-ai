import { useEffect, useRef } from 'react';

interface TurnstileApi {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  remove: (widgetId: string) => void;
}

interface TurnstileWindow extends Window {
  turnstile?: TurnstileApi;
}

const SCRIPT_ID = 'hireshield-turnstile-script';
const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

/** Explicitly rendered Cloudflare Turnstile widget. No token is invented locally. */
export function Turnstile({
  siteKey,
  onToken,
  onError,
}: {
  siteKey: string;
  onToken: (token: string) => void;
  onError: (message: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const callbacks = useRef({ onToken, onError });
  callbacks.current = { onToken, onError };

  useEffect(() => {
    let cancelled = false;
    const browser = window as TurnstileWindow;

    const render = () => {
      if (cancelled || widgetId.current || !container.current || !browser.turnstile) return;
      try {
        widgetId.current = browser.turnstile.render(container.current, {
          sitekey: siteKey,
          callback: (token: string) => callbacks.current.onToken(token),
          'expired-callback': () => callbacks.current.onToken(''),
          'error-callback': () => callbacks.current.onError('Verification failed. Please reload and try again.'),
        });
      } catch {
        callbacks.current.onError('Verification could not be displayed. Please reload the page.');
      }
    };

    const handleError = () => callbacks.current.onError('Could not load security verification. Check your connection.');
    if (browser.turnstile) {
      render();
    } else {
      let script = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
      if (!script) {
        script = document.createElement('script');
        script.id = SCRIPT_ID;
        script.src = SCRIPT_URL;
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }
      script.addEventListener('load', render);
      script.addEventListener('error', handleError);
      return () => {
        cancelled = true;
        script?.removeEventListener('load', render);
        script?.removeEventListener('error', handleError);
        if (widgetId.current && browser.turnstile) {
          try {
            browser.turnstile.remove(widgetId.current);
          } catch {
            /* widget already removed */
          }
        }
      };
    }

    return () => {
      cancelled = true;
      if (widgetId.current && browser.turnstile) {
        try {
          browser.turnstile.remove(widgetId.current);
        } catch {
          /* widget already removed */
        }
      }
    };
  }, [siteKey]);

  return <div ref={container} data-turnstile="login" aria-label="Security verification" />;
}

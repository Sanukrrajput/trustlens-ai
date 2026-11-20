import { useEffect, useRef, useState, type FormEvent } from 'react';
import { AlertCircle, Bot, CheckCircle2, MessageCircle, Send, Trash2, X } from 'lucide-react';
import { supportApi } from '../lib/api';
import type { SupportChatMessage as StoredMessage } from '../types';
import { cx } from '../lib/utils';

const SESSION_KEY = 'trustlens.support_session';
const SESSION_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;

const INITIAL_SUGGESTIONS = [
  'How is the risk score calculated?',
  'What should I do with an inconclusive result?',
  'Are scheduled monitoring jobs running?',
];

function createSessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '');
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random()
    .toString(36)
    .slice(2)}`.slice(0, 64);
}

function getSessionId(): string {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(SESSION_KEY) : null;
  if (stored && SESSION_PATTERN.test(stored)) return stored;
  const generated = createSessionId();
  if (typeof localStorage !== 'undefined') localStorage.setItem(SESSION_KEY, generated);
  return generated;
}

function welcomeMessage(sessionId: string): StoredMessage {
  return {
    id: 'welcome',
    session_id: sessionId,
    role: 'assistant',
    text: 'Hi — I can answer common TrustLens questions from the project documentation. I won’t guess or invent an answer.',
    grounded: true,
    suggestions: INITIAL_SUGGESTIONS,
    created_at: new Date().toISOString(),
  };
}

function localId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function SupportWidget() {
  const [sessionId] = useState(getSessionId);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    setLoadingHistory(true);
    supportApi
      .history(sessionId)
      .then((stored) => {
        if (!active) return;
        setMessages(stored.length ? stored : [welcomeMessage(sessionId)]);
        setHistoryError(false);
      })
      .catch(() => {
        if (!active) return;
        setMessages([welcomeMessage(sessionId)]);
        setHistoryError(true);
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (open && typeof endRef.current?.scrollIntoView === 'function') {
      endRef.current.scrollIntoView({ block: 'end' });
    }
  }, [messages, open, busy]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy || loadingHistory) return;

    setMessages((current) => [
      ...current,
      {
        id: localId('user'),
        session_id: sessionId,
        role: 'user',
        text: trimmed,
        created_at: new Date().toISOString(),
      },
    ]);
    setInput('');
    setBusy(true);

    try {
      const reply = await supportApi.ask({ message: trimmed, session_id: sessionId });
      setMessages((current) => [
        ...current,
        {
          id: reply.id,
          session_id: reply.session_id,
          role: 'assistant',
          text: reply.answer,
          grounded: reply.grounded,
          matched_question: reply.matched_question ?? null,
          sources: reply.sources ?? [],
          suggestions: reply.suggestions ?? [],
          created_at: reply.created_at,
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: localId('error'),
          session_id: sessionId,
          role: 'assistant',
          text: 'The support service is unavailable right now. Please try again shortly.',
          grounded: false,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function clearChat() {
    if (clearing) return;
    setClearing(true);
    try {
      await supportApi.clear(sessionId);
      setMessages([welcomeMessage(sessionId)]);
      setHistoryError(false);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: localId('clear-error'),
          session_id: sessionId,
          role: 'assistant',
          text: 'I could not clear the saved conversation. Please try again.',
          grounded: false,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setClearing(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(input);
  }

  return (
    <div className="fixed bottom-4 left-4 z-[90] flex flex-col items-start gap-3 sm:bottom-5 sm:left-5">
      {open && (
        <section
          role="dialog"
          aria-label="TrustLens support assistant"
          className="flex max-h-[min(72vh,34rem)] w-[min(92vw,25rem)] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
        >
          <header className="flex items-start gap-3 border-b border-line bg-elevated px-4 py-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500">
              <Bot className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-bold text-ink">TrustLens support</h2>
              <p className="mt-0.5 text-[11px] text-muted">Docs-backed answers · no guessing</p>
            </div>
            <button
              type="button"
              aria-label="Clear chat"
              title="Clear saved conversation"
              disabled={clearing || loadingHistory}
              onClick={() => void clearChat()}
              className="rounded-lg p-1.5 text-muted transition hover:bg-surface hover:text-danger disabled:opacity-40"
            >
              <Trash2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="Minimize support chat"
              title="Minimize"
              onClick={() => setOpen(false)}
              className="rounded-lg p-1.5 text-muted transition hover:bg-surface hover:text-ink"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
            {loadingHistory && (
              <div className="space-y-2" role="status">
                <p className="text-xs text-muted">Loading your saved conversation…</p>
                <div className="h-3 w-3/4 animate-pulse rounded bg-elevated" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-elevated" />
              </div>
            )}
            {historyError && (
              <p className="rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] text-warn">
                Saved history could not be loaded. Showing a fresh conversation.
              </p>
            )}

            {messages.map((message, index) => {
              const isUser = message.role === 'user';
              const isLatest = index === messages.length - 1;
              return (
                <div
                  key={message.id}
                  className={cx('flex w-full gap-2', isUser ? 'justify-end' : 'justify-start')}
                >
                  {!isUser && (
                    <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-500">
                      <Bot className="h-3.5 w-3.5" />
                    </span>
                  )}
                  <div
                    className={cx(
                      'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
                      isUser
                        ? 'bg-brand-600 text-white'
                        : 'border border-line bg-elevated text-ink',
                    )}
                  >
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <span
                        className={cx(
                          'text-[10px] font-bold uppercase tracking-wide',
                          isUser ? 'text-white/70' : 'text-muted',
                        )}
                      >
                        {isUser ? 'You' : 'TrustLens support'}
                      </span>
                      {!!message.created_at && (
                        <span
                          className={cx(
                            'text-[10px]',
                            isUser ? 'text-white/60' : 'text-muted',
                          )}
                        >
                          {formatTime(message.created_at)}
                        </span>
                      )}
                    </div>

                    <p className="whitespace-pre-wrap">{message.text}</p>

                    {!isUser && message.grounded !== undefined && message.grounded !== null && (
                      <span
                        className={cx(
                          'mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold',
                          message.grounded
                            ? 'bg-safe/10 text-safe'
                            : 'bg-warn/10 text-warn',
                        )}
                      >
                        {message.grounded ? (
                          <CheckCircle2 className="h-3 w-3" />
                        ) : (
                          <AlertCircle className="h-3 w-3" />
                        )}
                        {message.grounded ? 'Grounded in docs' : 'No grounded answer'}
                      </span>
                    )}

                    {!!message.sources?.length && (
                      <p className="mt-2 text-[10px] text-muted">
                        Sources: {message.sources.join(' · ')}
                      </p>
                    )}

                    {isLatest && !isUser && !busy && !!message.suggestions?.length && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {message.suggestions.map((suggestion) => (
                          <button
                            key={suggestion}
                            type="button"
                            onClick={() => void ask(suggestion)}
                            className="rounded-full border border-brand-500/30 bg-brand-500/5 px-2.5 py-1 text-[11px] font-semibold text-brand-700 transition hover:bg-brand-500/10 dark:text-brand-300"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {busy && (
              <div className="flex items-center gap-2 text-xs text-muted" role="status">
                <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
                Checking the documentation…
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form onSubmit={submit} className="flex items-center gap-2 border-t border-line p-3">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              maxLength={1000}
              aria-label="Ask a question"
              placeholder="Ask about scoring, billing, data…"
              disabled={loadingHistory}
              className="min-w-0 flex-1 rounded-xl border border-line bg-elevated px-3 py-2 text-sm text-ink outline-none placeholder:text-muted focus:border-brand-500 disabled:opacity-60"
            />
            <button
              type="submit"
              aria-label="Send question"
              disabled={busy || loadingHistory || !input.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>

          <p className="border-t border-line px-4 py-2 text-[10px] leading-snug text-muted">
            Saved with a random browser session ID so you can return later. Clearing removes it;
            messages also expire after 30 days. No card, PAN or KYC data.
          </p>
        </section>
      )}

      <button
        type="button"
        aria-label={open ? 'Close support chat' : 'Open support chat'}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-4 py-3 text-sm font-bold text-white shadow-card transition hover:bg-brand-500"
      >
        {open ? <X className="h-4 w-4" /> : <MessageCircle className="h-4 w-4" />}
        {open ? 'Hide chat' : 'Ask TrustLens'}
      </button>
    </div>
  );
}

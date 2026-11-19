import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Bot, MessageCircle, Send, X } from 'lucide-react';
import { supportApi } from '../lib/api';
import { cx } from '../lib/utils';

interface ChatMessage {
  id: number;
  role: 'assistant' | 'user';
  text: string;
  grounded?: boolean;
  sources?: string[];
  suggestions?: string[];
}

const INITIAL_SUGGESTIONS = [
  'How is the risk score calculated?',
  'What should I do with an inconclusive result?',
  'Are scheduled monitoring jobs running?',
];

export function SupportWidget() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 0,
      role: 'assistant',
      text: 'Hi — I can answer common HireShield questions from the project documentation. I won’t guess or invent an answer.',
      grounded: true,
      suggestions: INITIAL_SUGGESTIONS,
    },
  ]);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && typeof endRef.current?.scrollIntoView === 'function') {
      endRef.current.scrollIntoView({ block: 'end' });
    }
  }, [messages, open, busy]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;

    setMessages((current) => [
      ...current,
      { id: nextId.current++, role: 'user', text: trimmed },
    ]);
    setInput('');
    setBusy(true);

    try {
      const reply = await supportApi.ask({ message: trimmed });
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: 'assistant',
          text: reply.answer,
          grounded: reply.grounded,
          sources: reply.sources ?? [],
          suggestions: reply.suggestions ?? [],
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: 'assistant',
          text: 'The support service is unavailable right now. Please try again shortly.',
          grounded: false,
        },
      ]);
    } finally {
      setBusy(false);
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
          aria-label="HireShield support assistant"
          className="flex max-h-[min(70vh,32rem)] w-[min(92vw,24rem)] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
        >
          <header className="flex items-start gap-3 border-b border-line bg-elevated px-4 py-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500">
              <Bot className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-bold text-ink">HireShield support</h2>
              <p className="mt-0.5 text-[11px] text-muted">Docs-backed answers · no guessing</p>
            </div>
            <button
              type="button"
              aria-label="Close support chat"
              className="rounded-lg p-1.5 text-muted hover:bg-surface hover:text-ink"
              onClick={() => setOpen(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cx('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                <div
                  className={cx(
                    'max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
                    message.role === 'user'
                      ? 'bg-brand-600 text-white'
                      : 'border border-line bg-elevated text-ink',
                  )}
                >
                  <p className="whitespace-pre-wrap">{message.text}</p>
                  {message.role === 'assistant' && message.grounded !== undefined && (
                    <p
                      className={cx(
                        'mt-2 text-[10px] font-bold uppercase tracking-wide',
                        message.grounded ? 'text-safe' : 'text-warn',
                      )}
                    >
                      {message.grounded ? 'Grounded in docs' : 'No grounded answer'}
                    </p>
                  )}
                  {!!message.sources?.length && (
                    <p className="mt-1 text-[10px] text-muted">
                      Sources: {message.sources.join(', ')}
                    </p>
                  )}
                  {!!message.suggestions?.length && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {message.suggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          disabled={busy}
                          onClick={() => void ask(suggestion)}
                          className="rounded-full border border-brand-500/30 bg-brand-500/5 px-2.5 py-1 text-[11px] font-semibold text-brand-700 hover:bg-brand-500/10 disabled:opacity-50 dark:text-brand-300"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <p className="text-xs text-muted">Checking the documentation…</p>}
            <div ref={endRef} />
          </div>

          <form onSubmit={submit} className="flex items-center gap-2 border-t border-line p-3">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              maxLength={1000}
              aria-label="Ask a question"
              placeholder="Ask about scoring, billing, data…"
              className="min-w-0 flex-1 rounded-xl border border-line bg-elevated px-3 py-2 text-sm text-ink outline-none placeholder:text-muted focus:border-brand-500"
            />
            <button
              type="submit"
              aria-label="Send question"
              disabled={busy || !input.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white transition hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
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
        {open ? 'Close' : 'Ask HireShield'}
      </button>
    </div>
  );
}

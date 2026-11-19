import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SupportWidget } from '../components/SupportWidget';
import { supportApi } from '../lib/api';

vi.mock('../lib/api', () => ({
  supportApi: {
    ask: vi.fn(),
    history: vi.fn(),
    clear: vi.fn(),
  },
}));

const askMock = vi.mocked(supportApi.ask);
const historyMock = vi.mocked(supportApi.history);
const clearMock = vi.mocked(supportApi.clear);

const SESSION = 'test-session-123456';
const CREATED = '2026-01-01T10:00:00.000Z';

beforeEach(() => {
  askMock.mockReset();
  historyMock.mockReset();
  clearMock.mockReset();
  historyMock.mockResolvedValue([]);
  clearMock.mockResolvedValue({ status: 'cleared', session_id: SESSION, deleted: 2 });
});

describe('SupportWidget', () => {
  it('sends a question with its session ID and shows the grounded answer', async () => {
    askMock.mockResolvedValue({
      id: 'assistant-1',
      answer: 'Risk is weighted from multiple independent signals.',
      grounded: true,
      matched_question: 'How is the risk score calculated?',
      sources: ['README.md'],
      session_id: SESSION,
      created_at: CREATED,
    });

    const user = userEvent.setup();
    render(<SupportWidget />);

    await user.click(screen.getByRole('button', { name: 'Open support chat' }));
    await user.type(screen.getByLabelText('Ask a question'), 'How is the risk score calculated?');
    await user.click(screen.getByRole('button', { name: 'Send question' }));

    expect(
      await screen.findByText('Risk is weighted from multiple independent signals.'),
    ).toBeTruthy();
    expect(screen.getAllByText('Grounded in docs').length).toBeGreaterThan(0);
    expect(askMock).toHaveBeenCalledWith({
      message: 'How is the risk score calculated?',
      session_id: expect.stringMatching(/^[A-Za-z0-9_-]{8,64}$/),
    });
  });

  it('shows an honest fallback when the assistant has no grounded answer', async () => {
    askMock.mockResolvedValue({
      id: 'assistant-2',
      answer: 'I don’t have a grounded answer for that yet.',
      grounded: false,
      suggestions: ['Can I correct an assessment?'],
      session_id: SESSION,
      created_at: CREATED,
    });

    const user = userEvent.setup();
    render(<SupportWidget />);

    await user.click(screen.getByRole('button', { name: 'Open support chat' }));
    await user.type(screen.getByLabelText('Ask a question'), 'What is the weather in Delhi?');
    await user.click(screen.getByRole('button', { name: 'Send question' }));

    expect(await screen.findByText('I don’t have a grounded answer for that yet.')).toBeTruthy();
    expect(screen.getAllByText('No grounded answer').length).toBeGreaterThan(0);
    expect(
      screen.getByRole('button', { name: 'Can I correct an assessment?' }),
    ).toBeTruthy();
  });

  it('restores a saved conversation on open', async () => {
    historyMock.mockResolvedValue([
      {
        id: 'saved-1',
        session_id: SESSION,
        role: 'user',
        text: 'Earlier question',
        created_at: CREATED,
      },
      {
        id: 'saved-2',
        session_id: SESSION,
        role: 'assistant',
        text: 'Earlier grounded answer',
        grounded: true,
        sources: ['docs/API.md'],
        created_at: CREATED,
      },
    ]);

    const user = userEvent.setup();
    render(<SupportWidget />);
    await user.click(screen.getByRole('button', { name: 'Open support chat' }));

    expect(await screen.findByText('Earlier grounded answer')).toBeTruthy();
    expect(screen.getByText('Earlier question')).toBeTruthy();
    expect(historyMock).toHaveBeenCalledWith(
      expect.stringMatching(/^[A-Za-z0-9_-]{8,64}$/),
    );
  });

  it('clears the saved conversation', async () => {
    historyMock.mockResolvedValue([
      {
        id: 'saved-3',
        session_id: SESSION,
        role: 'assistant',
        text: 'Saved answer to remove',
        grounded: true,
        created_at: CREATED,
      },
    ]);

    const user = userEvent.setup();
    render(<SupportWidget />);
    await user.click(screen.getByRole('button', { name: 'Open support chat' }));
    expect(await screen.findByText('Saved answer to remove')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: 'Clear chat' }));

    expect(
      await screen.findByText(/I can answer common HireShield questions/),
    ).toBeTruthy();
    expect(clearMock).toHaveBeenCalledWith(
      expect.stringMatching(/^[A-Za-z0-9_-]{8,64}$/),
    );
  });
});

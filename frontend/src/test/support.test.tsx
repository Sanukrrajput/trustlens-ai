import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SupportWidget } from '../components/SupportWidget';
import { supportApi } from '../lib/api';

vi.mock('../lib/api', () => ({
  supportApi: { ask: vi.fn() },
}));

const askMock = vi.mocked(supportApi.ask);

beforeEach(() => {
  askMock.mockReset();
});

describe('SupportWidget', () => {
  it('sends a question and shows the grounded answer', async () => {
    askMock.mockResolvedValue({
      answer: 'Risk is weighted from multiple independent signals.',
      grounded: true,
      matched_question: 'How is the risk score calculated?',
      sources: ['README.md'],
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
    expect(askMock).toHaveBeenCalledWith({ message: 'How is the risk score calculated?' });
  });

  it('shows an honest fallback when the assistant has no grounded answer', async () => {
    askMock.mockResolvedValue({
      answer: 'I don’t have a grounded answer for that yet.',
      grounded: false,
      suggestions: ['Can I correct an assessment?'],
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
});

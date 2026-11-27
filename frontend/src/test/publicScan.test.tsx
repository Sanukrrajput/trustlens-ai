import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { PublicScanPage } from '../pages/PublicScanPage';

function renderPublicScan() {
  return render(
    <MemoryRouter>
      <PublicScanPage />
    </MemoryRouter>,
  );
}

describe('public quick-scan page', () => {
  it('requires text or a URL before scanning', async () => {
    const user = userEvent.setup();
    renderPublicScan();

    await user.click(screen.getByRole('button', { name: /run quick scan/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/at least 20 characters/i);
    expect(screen.queryByText('Quick-scan result')).not.toBeInTheDocument();
  });

  it('runs entirely in the browser and shows explainable evidence', async () => {
    const user = userEvent.setup();
    renderPublicScan();

    await user.type(
      screen.getByLabelText(/offer or message text/i),
      'Limited time! Pay a small processing fee via gift card and send your OTP immediately.',
    );
    await user.type(screen.getByLabelText(/source url/i), 'http://paypa1.example.com/verify');
    await user.click(screen.getByRole('button', { name: /run quick scan/i }));

    expect(await screen.findByText('Quick-scan result')).toBeInTheDocument();
    expect(screen.getByText(/advance payment requested/i)).toBeInTheDocument();
    expect(screen.getByText(/what was not checked/i)).toBeInTheDocument();
    expect(screen.getAllByText(/threat-intelligence feeds/i).length).toBeGreaterThan(0);
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '../context/ToastContext';
import { analysisApi, resolveAnalysis } from '../lib/api';
import { ScannerPage } from '../pages/ScannerPage';
import type { AnalysisResult, TaskStatusOut } from '../types';

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return {
    ...actual,
    analysisApi: {
      submitJob: vi.fn(),
      submitOffer: vi.fn(),
      submitMessage: vi.fn(),
      submitUrl: vi.fn(),
      submitDocument: vi.fn(),
      get: vi.fn(),
      list: vi.fn(),
    },
    resolveAnalysis: vi.fn(),
  };
});

const task: TaskStatusOut = { task_id: 'task-1', status: 'pending' };

function renderScanner() {
  return render(
    <MemoryRouter initialEntries={['/app/scan']}>
      <ToastProvider>
        <Routes>
          <Route path="/app/scan" element={<ScannerPage />} />
          <Route path="/app/reports/:id" element={<div>Report opened</div>} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('analysis workflow', () => {
  beforeEach(() => {
    vi.mocked(analysisApi.submitJob).mockReset().mockResolvedValue(task);
    vi.mocked(analysisApi.submitOffer).mockReset().mockResolvedValue(task);
    vi.mocked(resolveAnalysis).mockReset().mockResolvedValue({ id: 'report-1', status: 'completed' });
  });

  it('blocks submission when the job text is too short', async () => {
    const user = userEvent.setup();
    renderScanner();

    await user.type(screen.getByLabelText(/job description/i), 'short post');
    await user.click(screen.getByRole('button', { name: /run analysis/i }));

    expect(await screen.findByText(/paste at least 20 characters/i)).toBeInTheDocument();
    expect(analysisApi.submitJob).not.toHaveBeenCalled();
  });

  it('submits a job with consent and opens the resolved report', async () => {
    const user = userEvent.setup();
    renderScanner();

    const description = 'Remote operations associate. No interview required. Salary is competitive and equipment is provided after onboarding.';
    await user.type(screen.getByLabelText(/job description/i), description);
    await user.type(screen.getByLabelText(/claimed company/i), 'Example Ltd');
    await user.click(screen.getByRole('checkbox', { name: /allow external lookups/i }));
    await user.click(screen.getByRole('button', { name: /run analysis/i }));

    expect(await screen.findByText('Report opened')).toBeInTheDocument();
    await waitFor(() => expect(analysisApi.submitJob).toHaveBeenCalledTimes(1));
    expect(analysisApi.submitJob).toHaveBeenCalledWith(
      expect.objectContaining({
        text: description,
        company_name: 'Example Ltd',
        consent_external_lookups: true,
      }),
    );
    expect(resolveAnalysis).toHaveBeenCalledWith(task);
  });

  it('validates URLs before submitting a URL analysis', async () => {
    const user = userEvent.setup();
    renderScanner();

    await user.click(screen.getByRole('tab', { name: /^url$/i }));
    await user.type(screen.getByLabelText(/url to analyse/i), 'not-a-url');
    await user.click(screen.getByRole('button', { name: /run analysis/i }));

    expect(await screen.findByText(/enter a valid http\(s\) url/i)).toBeInTheDocument();
    expect(analysisApi.submitUrl).not.toHaveBeenCalled();
  });

  it('submits a generic offer with its category and opens the report', async () => {
    const user = userEvent.setup();
    vi.mocked(analysisApi.submitOffer).mockResolvedValue(task);
    renderScanner();

    await user.click(screen.getByRole('tab', { name: /^offer$/i }));
    const description = 'Congratulations! You have won a guaranteed prize. Share this post with 10 friends and pay a small processing fee to claim your reward today.';
    await user.type(screen.getByLabelText(/offer text/i), description);
    await user.selectOptions(screen.getByLabelText(/offer category/i), 'giveaway');
    await user.click(screen.getByRole('button', { name: /run analysis/i }));

    expect(await screen.findByText('Report opened')).toBeInTheDocument();
    await waitFor(() => expect(analysisApi.submitOffer).toHaveBeenCalledTimes(1));
    expect(analysisApi.submitOffer).toHaveBeenCalledWith(
      expect.objectContaining({ text: description, offer_category: 'giveaway' }),
    );
  });

  it('blocks an offer submission with too little text', async () => {
    const user = userEvent.setup();
    renderScanner();

    await user.click(screen.getByRole('tab', { name: /^offer$/i }));
    await user.type(screen.getByLabelText(/offer text/i), 'short');
    await user.click(screen.getByRole('button', { name: /run analysis/i }));

    expect(await screen.findByText(/paste at least 20 characters of the offer/i)).toBeInTheDocument();
    expect(analysisApi.submitOffer).not.toHaveBeenCalled();
  });

  it('passes an immediate analysis result through without blocking', async () => {
    const user = userEvent.setup();
    const immediate = { id: 'result-1', status: 'completed' } as AnalysisResult;
    vi.mocked(analysisApi.submitJob).mockResolvedValueOnce(immediate);
    vi.mocked(resolveAnalysis).mockResolvedValueOnce({ id: 'result-1', result: immediate, status: 'completed' });
    renderScanner();

    await user.type(screen.getByLabelText(/job description/i), 'A detailed legitimate job description with responsibilities, pay range and application steps.');
    await user.click(screen.getByRole('button', { name: /run analysis/i }));

    expect(await screen.findByText('Report opened')).toBeInTheDocument();
    expect(resolveAnalysis).toHaveBeenCalledWith(immediate);
  });
});

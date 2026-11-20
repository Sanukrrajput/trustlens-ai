import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { authApi } from '../lib/api';
import type { User } from '../types';
import { LoginPage } from '../pages/auth/LoginPage';
import { RegisterPage } from '../pages/auth/RegisterPage';

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return {
    ...actual,
    authApi: {
      login: vi.fn(),
      securityConfig: vi.fn(),
      signinActivity: vi.fn(),
      me: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    },
    getAccessToken: vi.fn(() => null),
    getStoredUser: vi.fn(() => null),
    setStoredUser: vi.fn(),
    setTokens: vi.fn(),
    clearTokens: vi.fn(),
  };
});

const mockUser: User = {
  id: 'user-1',
  email: 'asha@example.com',
  full_name: 'Asha Sharma',
  role: 'user',
  created_at: '2026-01-01T00:00:00Z',
};

const adminUser: User = {
  ...mockUser,
  id: 'admin-1',
  email: 'admin@hireshield.io',
  full_name: 'Platform Admin',
  role: 'admin',
};

function renderWithAuth(element: ReactNode) {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={element} />
          <Route path="/app" element={<div>Dashboard reached</div>} />
          <Route path="/app/admin" element={<div>Admin console reached</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('authentication flow', () => {
  afterEach(() => {
    Reflect.deleteProperty(window, 'turnstile');
  });

  beforeEach(() => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'access', refresh_token: 'refresh', token_type: 'bearer', expires_in: 3600 });
    vi.mocked(authApi.securityConfig).mockResolvedValue({
      enabled: false,
      status: 'not_configured',
      provider: 'cloudflare_turnstile',
      note: 'not configured',
    });
    vi.mocked(authApi.me).mockResolvedValue(mockUser);
    vi.mocked(authApi.register).mockResolvedValue(mockUser);
  });

  it('shows validation errors instead of calling login for invalid input', async () => {
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Email is required.')).toBeInTheDocument();
    expect(screen.getByText('Password is required.')).toBeInTheDocument();
    expect(authApi.login).not.toHaveBeenCalled();
  });

  it('signs in with valid credentials and navigates to the protected area', async () => {
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'asha@example.com');
    await user.type(screen.getByLabelText(/password/i), 'StrongPass123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Dashboard reached')).toBeInTheDocument();
    expect(authApi.login).toHaveBeenCalledWith(
      'asha@example.com',
      'StrongPass123',
      expect.objectContaining({ access_mode: 'user', device_id: expect.any(String), remember_device: false }),
    );
  });

  it('prefills remembered email and shows the previous sign-in context', async () => {
    localStorage.setItem('trustlens.remembered_signin', JSON.stringify({
      email: 'asha@example.com',
      device_id: 'device-alpha',
      previous_signin: {
        at: '2026-11-18T10:00:00Z',
        device: 'Chrome on Windows',
        ip_masked: '192.168.1.x',
      },
      saved_at: '2026-11-18T10:00:00Z',
    }));
    await act(async () => { renderWithAuth(<LoginPage />); });

    expect(screen.getByLabelText(/email address/i)).toHaveValue('asha@example.com');
    expect(screen.getByText(/Previous sign-in/)).toBeInTheDocument();
    expect(screen.getByText(/Chrome on Windows/)).toBeInTheDocument();
  });

  it('sends the Cloudflare token and remembered-device choice at sign in', async () => {
    Object.defineProperty(window, 'turnstile', {
      configurable: true,
      writable: true,
      value: {
        render: (_element: HTMLElement, options: { callback: (token: string) => void }) => {
          options.callback('cf-test-token');
          return 'widget-1';
        },
        remove: vi.fn(),
      },
    });
    vi.mocked(authApi.securityConfig).mockResolvedValueOnce({
      enabled: true,
      site_key: 'public-site-key',
      status: 'configured',
      provider: 'cloudflare_turnstile',
      note: 'Protected by Cloudflare Turnstile.',
    });
    localStorage.setItem('trustlens.remembered_signin', JSON.stringify({
      email: 'asha@example.com',
      saved_at: '2026-11-18T10:00:00Z',
    }));
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />);

    await user.type(screen.getByLabelText(/password/i), 'StrongPass123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Dashboard reached')).toBeInTheDocument();
    expect(authApi.login).toHaveBeenCalledWith(
      'asha@example.com',
      'StrongPass123',
      expect.objectContaining({
        turnstile_token: 'cf-test-token',
        remember_device: true,
        device_id: expect.any(String),
      }),
    );
  });

  it('offers separate user and admin sign-in options', async () => {
    const user = userEvent.setup();
    renderWithAuth(<LoginPage />);

    const userOption = screen.getByRole('button', { name: /user login/i });
    const adminOption = screen.getByRole('button', { name: /admin login/i });
    expect(userOption).toHaveAttribute('aria-pressed', 'true');
    expect(adminOption).toHaveAttribute('aria-pressed', 'false');

    await user.click(adminOption);

    expect(screen.getByRole('button', { name: /user login/i })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /admin login/i })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/Administrator sign-in/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /admin sign in/i })).toBeInTheDocument();
  });

  it('sends admin access mode and routes an administrator to the admin console', async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.me).mockResolvedValueOnce(adminUser);
    renderWithAuth(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /admin login/i }));
    await user.type(screen.getByLabelText(/email address/i), 'admin@hireshield.io');
    await user.type(screen.getByLabelText(/password/i), 'AdminPass123');
    await user.click(screen.getByRole('button', { name: /admin sign in/i }));

    expect(await screen.findByText('Admin console reached')).toBeInTheDocument();
    expect(authApi.login).toHaveBeenCalledWith(
      'admin@hireshield.io',
      'AdminPass123',
      expect.objectContaining({ access_mode: 'admin' }),
    );
  });

  it('does not grant admin access when a normal account selects Admin login', async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.login).mockRejectedValueOnce(new Error('this account does not have administrator access'));
    renderWithAuth(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /admin login/i }));
    await user.type(screen.getByLabelText(/email address/i), 'asha@example.com');
    await user.type(screen.getByLabelText(/password/i), 'StrongPass123');
    await user.click(screen.getByRole('button', { name: /admin sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('does not have administrator access');
    expect(screen.queryByText('Admin console reached')).not.toBeInTheDocument();
    expect(authApi.login).toHaveBeenCalledWith(
      'asha@example.com',
      'StrongPass123',
      expect.objectContaining({ access_mode: 'admin' }),
    );
  });

  it('requires both consents before registering', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText(/full name/i), 'Asha Sharma');
    await user.type(screen.getByLabelText(/email address/i), 'asha@example.com');
    await user.type(screen.getByLabelText(/password/i), 'StrongPass123');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByText('Please accept the privacy policy.')).toBeInTheDocument();
    expect(screen.getByText('Please accept the terms.')).toBeInTheDocument();
    expect(authApi.register).not.toHaveBeenCalled();
  });
});

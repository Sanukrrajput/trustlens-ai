import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CreateAccountForm } from '../components/CreateAccountForm';
import { adminApi } from '../lib/api';
import type { User } from '../types';

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>();
  return {
    ...actual,
    adminApi: {
      ...actual.adminApi,
      createUser: vi.fn(),
    },
  };
});

const createdUser: User = {
  id: 'created-1',
  email: 'new.admin@example.com',
  full_name: 'New Admin',
  role: 'admin',
  created_at: '2026-11-19T00:00:00Z',
};

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/full name/i), 'New Admin');
  await user.type(screen.getByLabelText(/email address/i), 'new.admin@example.com');
  await user.type(screen.getByLabelText(/organisation/i), 'Example Ltd');
  await user.type(screen.getByLabelText(/temporary password/i), 'CreatedAdmin123!');
}

describe('admin account provisioning', () => {
  beforeEach(() => {
    vi.mocked(adminApi.createUser).mockResolvedValue(createdUser);
  });

  it('creates an admin account and reports the result', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();
    render(<CreateAccountForm onCreated={onCreated} />);

    await fillForm(user);
    await user.selectOptions(screen.getByLabelText(/role/i), 'admin');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Created admin account for new.admin@example.com');
    expect(adminApi.createUser).toHaveBeenCalledWith(expect.objectContaining({
      email: 'new.admin@example.com',
      full_name: 'New Admin',
      organisation: 'Example Ltd',
      password: 'CreatedAdmin123!',
      role: 'admin',
    }));
    expect(onCreated).toHaveBeenCalledWith(createdUser);
    expect(screen.getByLabelText(/full name/i)).toHaveValue('');
  });

  it('shows the server rejection without pretending the account was created', async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.createUser).mockRejectedValueOnce(new Error('cannot create an account above your own role'));
    render(<CreateAccountForm />);

    await fillForm(user);
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('cannot create an account above your own role');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

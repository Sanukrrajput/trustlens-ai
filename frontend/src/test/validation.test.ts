import { describe, expect, it } from 'vitest';
import {
  validateCompany,
  validateFeedback,
  validateJob,
  validateLogin,
  validateMessage,
  validateMonitoring,
  validatePassword,
  validateRegister,
  validateUrl,
} from '../lib/validation';

describe('form validation', () => {
  it('requires valid credentials and privacy consent on registration', () => {
    const errors = validateRegister({
      email: 'not-an-email',
      password: 'short',
      full_name: 'A',
      consent_privacy: false,
      consent_terms: true,
    });
    expect(errors).toHaveProperty('email');
    expect(errors).toHaveProperty('password');
    expect(errors).toHaveProperty('full_name');
    expect(errors).toHaveProperty('consent_privacy');
    expect(errors).not.toHaveProperty('consent_terms');

    expect(
      validateRegister({
        email: 'asha@example.com',
        password: 'StrongPass123',
        full_name: 'Asha Sharma',
        consent_privacy: true,
        consent_terms: true,
      }),
    ).toEqual({});
  });

  it('enforces backend password rules', () => {
    expect(validatePassword('lowercaseonly1')).toMatch(/uppercase/i);
    expect(validatePassword('Short1Aa')).toMatch(/10 characters/);
    expect(validatePassword('StrongPass123')).toBeUndefined();
  });

  it('validates login fields', () => {
    expect(validateLogin({ email: '', password: '' })).toEqual({
      email: 'Email is required.',
      password: 'Password is required.',
    });
    expect(validateLogin({ email: 'user@example.com', password: 'pass' })).toEqual({});
  });

  it('validates each analysis input type', () => {
    expect(validateJob({ text: 'too short' })).toHaveProperty('text');
    expect(validateJob({ text: 'A'.repeat(30), source_url: 'not-a-url' })).toHaveProperty('source_url');
    expect(validateJob({ text: 'A'.repeat(30), recruiter_email: 'bad-email' })).toHaveProperty('recruiter_email');
    expect(validateJob({ text: 'A'.repeat(30) })).toEqual({});

    expect(validateMessage({ text: 'hi' })).toHaveProperty('text');
    expect(validateMessage({ text: 'Please review this remote role offer.' })).toEqual({});

    expect(validateUrl({ url: 'example.com' })).toHaveProperty('url');
    expect(validateUrl({ url: 'https://example.com/jobs/1' })).toEqual({});

    expect(validateCompany({ company_name: 'X' })).toHaveProperty('company_name');
    expect(validateCompany({ company_name: 'Example Ltd' })).toEqual({});
  });

  it('requires at least one monitoring target and valid source URLs', () => {
    expect(validateMonitoring({ name: 'Test', company_names: [], job_titles: [], keywords: [], source_urls: [] })).toHaveProperty('targets');
    expect(
      validateMonitoring({ name: 'Test', company_names: ['Example'], job_titles: [], keywords: [], source_urls: ['bad'] }),
    ).toHaveProperty('source_urls');
    expect(
      validateMonitoring({ name: 'Test', company_names: ['Example'], job_titles: [], keywords: [], source_urls: ['https://example.com'] }),
    ).toEqual({});
  });

  it('requires actionable correction details', () => {
    expect(validateFeedback({ details: 'wrong' })).toHaveProperty('details');
    expect(validateFeedback({ details: 'The company name was incorrectly matched to another entity.' })).toEqual({});
  });
});

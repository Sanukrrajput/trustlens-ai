import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, isPublicStaticBuild } from '../lib/api';

const originalLocation = window.location;

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
  vi.restoreAllMocks();
});

describe('public static API guard', () => {
  it('does not fetch from a github.io Pages origin', async () => {
    Object.defineProperty(window, 'location', {
      value: { hostname: 'sanukrrajput.github.io' },
      configurable: true,
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    expect(isPublicStaticBuild()).toBe(true);
    await expect(api('/billing/plans')).rejects.toBeInstanceOf(ApiError);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('keeps normal same-origin API behaviour outside Pages', () => {
    expect(isPublicStaticBuild()).toBe(false);
  });
});

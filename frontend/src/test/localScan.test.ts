import { describe, expect, it } from 'vitest';
import { scanOfferLocally } from '../lib/localScan';
import { FALLBACK_PLANS } from '../lib/plans';

const fixedNow = new Date('2026-01-01T00:00:00.000Z');

describe('public quick scan', () => {
  it('scores advance-fee and lookalike-domain patterns as high risk', () => {
    const result = scanOfferLocally(
      {
        text: 'Limited time! Pay a small processing fee of Rs 500 via gift card. Send your bank account and OTP immediately.',
        url: 'http://paypa1.example.com/verify',
        companyName: 'Example Ltd',
      },
      fixedNow,
    );

    expect(result.risk.score).toBeGreaterThanOrEqual(70);
    expect(result.risk.category).toBe('high');
    expect(result.indicators.map((item) => item.name)).toContain('Advance payment requested');
    expect(result.indicators.map((item) => item.name)).toContain('Gift-card or voucher payment');
    expect(result.indicators.map((item) => item.name)).toContain('Possible brand misspelling in domain');
    expect(result.risk.unavailable_signals).toContain('Threat-intelligence feeds');
    expect(result.model_predictions[0]?.model_name).toBe('offer_rule_fallback');
  });

  it('returns a low score and keeps unavailable checks visible for a plain https offer', () => {
    const result = scanOfferLocally(
      {
        text: 'Join our community webinar on Saturday. Register for free at the official events page. No payment is required.',
        url: 'https://exampleevents.com/webinar',
        companyName: 'Example Events',
      },
      fixedNow,
    );

    expect(result.risk.score).toBeLessThan(20);
    expect(result.risk.category).toBe('minimal');
    expect(result.indicators.map((item) => item.name)).toContain('Encrypted link syntax');
    expect(result.missing_evidence).toContain('Community and complaint history');
    expect(result.risk.data_coverage).toBeCloseTo(0.8);
  });
});

describe('static pricing fallback', () => {
  it('publishes the chosen Enterprise price instead of Rs 0', () => {
    const enterprise = FALLBACK_PLANS.find((plan) => plan.code === 'enterprise');
    expect(enterprise?.price_monthly_paise).toBe(299900);
    expect(enterprise?.price_yearly_paise).toBe(2999000);
  });
});

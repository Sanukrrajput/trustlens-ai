import type { AnalysisResult } from '../types';

/**
 * Landing-page illustration only. Every value below is fictional and must always
 * render underneath a visible "DEMO DATA — NOT A REAL ASSESSMENT" label.
 */
export const DEMO_LABEL = 'DEMO DATA — NOT A REAL ASSESSMENT';

export const demoAnalysis: AnalysisResult = {
  id: 'demo-0000-0000',
  analysis_type: 'job',
  status: 'completed',
  user_id: 'demo-user',
  created_at: '2026-01-15T09:30:00Z',
  completed_at: '2026-01-15T09:30:04Z',
  input_preview:
    'Remote Operations Associate — Northstar Talent Group. Immediate start. No interview required. Pay a refundable onboarding fee of $295 via gift cards to reserve your workstation…',
  extracted: {
    company_names: ['Northstar Talent Group (fictional)'],
    job_titles: ['Remote Operations Associate'],
    salary: '$52,000 – $68,000 (claimed)',
    recruiter_emails: ['careers@northstar-example.invalid'],
    phone_numbers: ['+1-555-010-0199'],
    urls: ['https://northstar-example.invalid/apply'],
    payment_demands: ['$295 onboarding fee via gift cards'],
    sensitive_data_requests: ['SSN', 'bank account details', 'passport scan'],
    locations: ['Remote — US'],
  },
  model_predictions: [
    {
      model_name: 'lexical-risk-classifier',
      model_version: 'demo-1.0',
      prediction: 'high_risk',
      fraud_probability: 0.86,
      confidence: 0.82,
      contributing_features: [
        { feature: 'advance_fee_language', impact: 0.34 },
        { feature: 'urgency_pressure', impact: 0.21 },
        { feature: 'payment_via_gift_card', impact: 0.19 },
      ],
      limitations: ['Illustrative values only.', 'No real text was classified.'],
    },
    {
      model_name: 'intent-anomaly-detector',
      model_version: 'demo-1.0',
      prediction: 'suspicious',
      fraud_probability: 0.71,
      confidence: 0.68,
      contributing_features: [{ feature: 'no_interview_claim', impact: 0.28 }],
      limitations: ['Illustrative values only.'],
    },
  ],
  domain_intelligence: {
    domain_age_days: 12,
    registrar: 'Fictional registrar',
    ssl_valid: true,
    note: 'Illustrative domain signals for a domain that does not exist.',
  },
  company_intelligence: {
    registry_match: false,
    name: 'Northstar Talent Group (fictional)',
    note: 'Illustrative registry lookup — no registry was queried.',
  },
  message_intelligence: {
    urgency_markers: ['immediate start', 'limited slots'],
    tone: 'pressure',
    note: 'Illustrative message analysis.',
  },
  historical_intelligence: {
    prior_reports: 3,
    first_seen: '2026-01-10',
    note: 'Illustrative historical signals.',
  },
  indicators: [
    {
      name: 'Advance payment requested',
      status: 'confirmed_malicious',
      severity: 0.95,
      description: 'The message requests a gift-card payment before any employment contract is signed.',
      source: 'Demo rule engine',
      reference_url: null,
      observed_at: '2026-01-15T09:30:00Z',
      confidence: 0.94,
      independently_verified: true,
      expires_at: null,
      weight: 1.8,
    },
    {
      name: 'Company registry mismatch',
      status: 'verified_inconsistency',
      severity: 0.8,
      description: 'The claimed legal entity does not appear in the illustrative corporate registry sample.',
      source: 'Demo registry fixture',
      reference_url: null,
      observed_at: '2026-01-15T09:31:00Z',
      confidence: 0.88,
      independently_verified: true,
      expires_at: null,
      weight: 1.4,
    },
    {
      name: 'Unverifiable recruiter identity',
      status: 'suspicious',
      severity: 0.65,
      description: 'Sender domain does not match the claimed employer domain.',
      source: 'Demo domain check',
      reference_url: null,
      observed_at: '2026-01-15T09:32:00Z',
      confidence: 0.7,
      independently_verified: false,
      expires_at: null,
      weight: 1.1,
    },
    {
      name: 'Sensitive data requested early',
      status: 'suspicious',
      severity: 0.72,
      description: 'Bank details and identity documents requested before an offer is formalised.',
      source: 'Demo extraction',
      reference_url: null,
      observed_at: '2026-01-15T09:33:00Z',
      confidence: 0.76,
      independently_verified: false,
      expires_at: null,
      weight: 1.2,
    },
    {
      name: 'Employer LinkedIn verification',
      status: 'unverified',
      severity: 0.35,
      description: 'No matching company page could be located in the illustrative sample.',
      source: 'Demo social check',
      reference_url: null,
      observed_at: '2026-01-15T09:34:00Z',
      confidence: 0.5,
      independently_verified: false,
      expires_at: null,
      weight: 0.7,
    },
    {
      name: 'Verified careers page present',
      status: 'supportive',
      severity: 0.2,
      description: 'A careers site exists, but it does not mention the advertised role.',
      source: 'Demo web check',
      reference_url: null,
      observed_at: '2026-01-15T09:35:00Z',
      confidence: 0.62,
      independently_verified: false,
      expires_at: null,
      weight: 0.5,
    },
    {
      name: 'Corporate registry access',
      status: 'technical_limitation',
      severity: 0.3,
      description: 'Registry lookup was simulated and cannot be treated as evidence.',
      source: 'Demo environment',
      reference_url: null,
      observed_at: '2026-01-15T09:36:00Z',
      confidence: 1,
      independently_verified: false,
      expires_at: null,
      weight: 0.2,
    },
  ],
  missing_evidence: [
    'Signed employment contract',
    'Verified corporate registration number',
    'Consistent recruiter identity across channels',
  ],
  technical_limitations: [
    'External lookups were simulated for this demonstration.',
    'No live domain, registry or historical data was queried.',
  ],
  risk: {
    score: 78,
    category: 'high_risk',
    inconclusive: false,
    summary:
      'This fictional example shows how HireShield combines extracted signals, model predictions and independently verified evidence into an explainable risk score.',
    evidence_summary: [
      'Advance-fee request is the strongest negative signal.',
      'Several identity claims remain unverified.',
    ],
    recommended_actions: [
      'Never pay a recruiter for a job offer or equipment.',
      'Verify the employer through an official website and independent registry.',
      'Report the message to the platform where you received it.',
    ],
    confidence: 0.84,
    data_coverage: 0.71,
    weights_version: 'demo-weights-1',
    component_scores: {
      payment_signals: 0.92,
      identity_consistency: 0.74,
      domain_signals: 0.68,
      message_pressure: 0.81,
    },
  },
  sources_attempted: ['Demo extraction', 'Demo domain check', 'Demo registry fixture', 'Demo web check'],
  sources_succeeded: ['Demo extraction', 'Demo domain check', 'Demo registry fixture', 'Demo web check'],
  report_id: null,
};

export const demoFaqs = [
  {
    question: 'Is HireShield a replacement for my own judgement?',
    answer:
      'No. HireShield surfaces evidence and confidence, not certainty. An inconclusive result is a valid outcome and always means you should seek independent confirmation before acting.',
  },
  {
    question: 'Do you guarantee that a job is legitimate?',
    answer:
      'No service can guarantee this. We combine public signals, extraction and models, and clearly label missing evidence and technical limitations so you can judge the strength of each finding.',
  },
  {
    question: 'Will a single suspicious word make a listing high risk?',
    answer:
      'No. Risk is calculated from weighted evidence across multiple dimensions. Corroborated, independently verified indicators carry more weight than isolated or unverified signals.',
  },
  {
    question: 'Can I correct an assessment?',
    answer:
      'Yes. Signed-in users can submit a report with supporting context from any investigation report. Corrections are reviewed and feed into future model and rule improvements.',
  },
];

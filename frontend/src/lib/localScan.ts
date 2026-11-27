import type {
  AnalysisResult,
  EvidenceIndicator,
  EvidenceStatus,
  OfferCategory,
} from '../types';

/**
 * Public, browser-only quick scan.
 *
 * This engine deliberately uses transparent text and URL-syntax rules. It never
 * contacts a server, registry, threat feed or community database, and it does
 * not claim that a trained general-offer model was used.
 */

type SignalCategory = 'content' | 'url' | 'brand' | 'threat' | 'community' | 'coverage';

export interface LocalScanInput {
  text: string;
  url?: string;
  companyName?: string;
  category?: OfferCategory;
}

interface Finding {
  indicator: EvidenceIndicator;
  points: number;
}

interface ContentRule {
  name: string;
  pattern: RegExp;
  severity: number;
  points: number;
  description: string;
  confidence: number;
}

const contentRules: ContentRule[] = [
  {
    name: 'Advance payment requested',
    pattern: /\b(?:advance|upfront|processing|registration|activation|onboarding|handling|security|verification|application|administrative)\s+(?:fee|payment|charge)\b/i,
    severity: 0.95,
    points: 36,
    description: 'The text asks for a fee or charge before the offer has been independently verified.',
    confidence: 0.93,
  },
  {
    name: 'Payment demanded before verification',
    pattern: /\bpay\s+(?:a\s+)?(?:(?:small|nominal|refundable|processing|handling|security|verification|application|administrative)\s+)*(?:fee|amount|charge)\b/i,
    severity: 0.9,
    points: 32,
    description: 'A payment is requested as a condition of continuing the offer.',
    confidence: 0.9,
  },
  {
    name: 'Gift-card or voucher payment',
    pattern: /\b(?:gift\s*card|voucher|redeem\s*code|prepaid\s*card)\b/i,
    severity: 0.95,
    points: 34,
    description: 'Gift cards and vouchers are common irreversible payment channels in offer fraud.',
    confidence: 0.92,
  },
  {
    name: 'Crypto or irreversible transfer requested',
    pattern: /\b(?:bitcoin|btc|ethereum|usdt|crypto(?:currency)?|western\s*union|money\s*gram)\b/i,
    severity: 0.9,
    points: 30,
    description: 'The text mentions a payment channel that is difficult to reverse or trace.',
    confidence: 0.88,
  },
  {
    name: 'Urgency or scarcity pressure',
    pattern: /\b(?:act\s+now|limited[ -]?time|today\s+only|last\s+chance|expires?\s+(?:in|today|soon)|immediately|urgent|only\s+(?:a\s+few|few)\s+(?:slots|spots|hours))\b/i,
    severity: 0.65,
    points: 16,
    description: 'Pressure to act quickly reduces the time available for independent verification.',
    confidence: 0.78,
  },
  {
    name: 'Too-good-to-be-true claim',
    pattern: /\b(?:guaranteed|no\s+questions\s+asked|double\s+your\s+money|free\s+gift\s*card|lottery|you\s+have\s+won|congratulations[!,]?\s+you)\b/i,
    severity: 0.75,
    points: 20,
    description: 'The offer makes an unusually absolute or reward-heavy claim.',
    confidence: 0.8,
  },
  {
    name: 'Unusual return promise',
    pattern: /\b(?:\d{1,3}\s*%\s*(?:per|a)\s*(?:day|week|month)|risk[-\s]?free\s+(?:profit|returns?)|earn\s+\d{2,}\s*%\s+daily)\b/i,
    severity: 0.8,
    points: 24,
    description: 'The text promises unusually high or risk-free returns.',
    confidence: 0.82,
  },
  {
    name: 'Sensitive data requested',
    pattern: /\b(?:bank\s+account|otp|one[-\s]?time\s+password|aadhaar|ssn|social\s+security|passport|cvv|card\s+number|password)\b/i,
    severity: 0.8,
    points: 24,
    description: 'Sensitive identity, banking or authentication data is mentioned in the offer.',
    confidence: 0.85,
  },
  {
    name: 'No interview or instant offer claim',
    pattern: /\b(?:no\s+interview|without\s+interview|immediate\s+(?:start|joining|offer)|no\s+experience\s+(?:required|needed))\b/i,
    severity: 0.7,
    points: 18,
    description: 'The process skips normal verification steps such as an interview or assessment.',
    confidence: 0.76,
  },
  {
    name: 'Authority or verification claim',
    pattern: /\b(?:government[-\s]?approved|officially\s+verified|certified\s+by|endorsed\s+by)\b/i,
    severity: 0.55,
    points: 12,
    description: 'The text claims authority or endorsement that this local scan cannot corroborate.',
    confidence: 0.62,
  },
];

function hash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(16).padStart(8, '0');
}

function collect(text: string, pattern: RegExp, limit = 5): string[] {
  const found = text.match(pattern) ?? [];
  return Array.from(new Set(found.map((item) => item.trim()).filter(Boolean))).slice(0, limit);
}

function normaliseUrl(value?: string): URL | null {
  const raw = value?.trim();
  if (!raw) return null;
  const candidate = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    return new URL(candidate);
  } catch {
    return null;
  }
}

function makeIndicator(
  name: string,
  status: EvidenceStatus,
  severity: number,
  description: string,
  confidence: number,
  category: SignalCategory,
  source: string,
  observedAt: string,
): EvidenceIndicator {
  return {
    name,
    status,
    severity,
    description,
    source,
    reference_url: null,
    observed_at: observedAt,
    confidence,
    independently_verified: false,
    expires_at: null,
    weight: Number((severity * confidence).toFixed(2)),
    signal_category: category,
  };
}

function riskBand(score: number): string {
  if (score >= 70) return 'high';
  if (score >= 45) return 'caution';
  if (score >= 20) return 'low';
  return 'minimal';
}

function summaryFor(score: number): string {
  if (score >= 70) {
    return 'Several high-weight local risk signals were found. Do not pay, share documents or provide OTPs until the source has been verified independently.';
  }
  if (score >= 45) {
    return 'Multiple caution signals were found. Check the organisation and the offer through an independent channel before acting.';
  }
  if (score >= 20) {
    return 'A few weak risk signals were found. A normal independent check is still advisable.';
  }
  return 'No strong local risk patterns were found. This is not proof that the offer is legitimate.';
}

export function scanOfferLocally(input: LocalScanInput, now: Date = new Date()): AnalysisResult {
  const text = input.text.trim();
  const urlValue = input.url?.trim() ?? '';
  const companyName = input.companyName?.trim() ?? '';
  const category = input.category ?? 'other';
  const parsedUrl = normaliseUrl(urlValue);
  const observedAt = now.toISOString();
  const findings: Finding[] = [];

  const add = (
    name: string,
    status: EvidenceStatus,
    severity: number,
    description: string,
    confidence: number,
    points: number,
    signalCategory: SignalCategory,
    source: string,
  ) => {
    findings.push({
      indicator: makeIndicator(name, status, severity, description, confidence, signalCategory, source, observedAt),
      points,
    });
  };

  contentRules.forEach((rule) => {
    if (rule.pattern.test(text)) {
      add(rule.name, 'suspicious', rule.severity, rule.description, rule.confidence, rule.points, 'content', 'Local text rules');
    }
  });

  const emails = collect(text, /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi);
  const urls = collect(`${text} ${urlValue}`, /\bhttps?:\/\/[^\s<>"']+/gi);
  const phones = collect(text, /\+?\d[\d\s-]{7,}\d/g);
  const paymentDemands = collect(text, /\b(?:pay|payment|fee|gift card|voucher|crypto|transfer|refundable)[^\n.]{0,90}/gi, 4);
  const sensitiveRequests = collect(text, /\b(?:bank account|otp|aadhaar|ssn|passport|cvv|card number|password)[^\n.]{0,60}/gi, 4);

  if (parsedUrl) {
    const host = parsedUrl.hostname.toLowerCase();
    const isIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(host) || host.includes(':');
    const hasPunycode = host.includes('xn--');
    const hasLookalike = /(?:paypa1|micros0ft|app1e|faceb00k|g00gle|amaz0n|1inkedin|payp[a@]1)/.test(host);
    const securePath = /\/(?:login|verify|secure|account|signin|auth|update)(?:\/|$)/i.test(parsedUrl.pathname);

    if (isIp) {
      add('URL uses a bare IP address', 'suspicious', 0.9, 'The link points directly to an IP address instead of a named domain.', 0.9, 38, 'url', 'Local URL syntax rules');
    }
    if (hasPunycode) {
      add('Unicode lookalike domain', 'suspicious', 0.85, 'The hostname uses encoded Unicode characters, which can impersonate a trusted brand.', 0.82, 30, 'url', 'Local URL syntax rules');
    }
    if (hasLookalike) {
      add('Possible brand misspelling in domain', 'suspicious', 0.95, 'The hostname contains a character-substitution pattern commonly used to imitate trusted brands.', 0.88, 42, 'url', 'Local URL syntax rules');
    }
    if (parsedUrl.protocol === 'http:') {
      add('Unencrypted link', 'suspicious', 0.55, 'The link uses http:// rather than https://, so transport encryption is not indicated.', 0.74, 14, 'url', 'Local URL syntax rules');
    }
    if (securePath) {
      add('Credential-style path', 'unverified', 0.5, 'The URL path resembles a sign-in or verification page; confirm it is the organisation’s real site.', 0.6, 10, 'url', 'Local URL syntax rules');
    }
    if (parsedUrl.protocol === 'https:' && !isIp && !hasPunycode && !hasLookalike) {
      add('Encrypted link syntax', 'supportive', 0.15, 'The supplied URL uses https:// with a named host. This is a weak positive signal only.', 0.7, -8, 'url', 'Local URL syntax rules');
    }

    if (companyName) {
      const stopWords = new Set(['ltd', 'limited', 'inc', 'llc', 'group', 'services', 'solutions', 'company', 'the', 'and']);
      const companyTokens = companyName
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter((token) => token.length > 3 && !stopWords.has(token));
      const hostTokens = host
        .replace(/\.[a-z]{2,}$/i, '')
        .split(/[.-]/)
        .filter((token) => token.length > 3 && !stopWords.has(token));
      const overlaps = companyTokens.some((token) => hostTokens.some((hostToken) => hostToken.includes(token) || token.includes(hostToken)));
      if (!overlaps && hostTokens.length > 0) {
        add('Claimed brand does not match URL', 'unverified', 0.8, 'The claimed company name shares no clear token with the URL hostname. It may still be a legitimate subdomain or partner site.', 0.65, 18, 'brand', 'Local brand-to-domain check');
      }
    }
  } else if (urlValue) {
    add('URL could not be parsed', 'unverified', 0.4, 'The supplied link was not valid URL syntax, so no hostname checks could run.', 0.75, 8, 'url', 'Local URL syntax rules');
  }

  if (emails.some((email) => /(?:gmail|yahoo|outlook|hotmail|icloud|aol|proton)/i.test(email))) {
    add('Generic sender domain', 'unverified', 0.65, 'A free email provider is used for a claim that may need organisation-level verification.', 0.72, 16, 'brand', 'Local contact check');
  }

  const pointsByCategory: Record<SignalCategory, number> = {
    content: 0,
    url: 0,
    brand: 0,
    threat: 0,
    community: 0,
    coverage: 0,
  };
  findings.forEach((finding) => {
    const categoryKey = finding.indicator.signal_category ?? 'content';
    pointsByCategory[categoryKey] += finding.points;
  });

  const brandAvailable = Boolean(companyName || emails.length > 0);
  const weights: Record<SignalCategory, number> = {
    content: 30,
    url: parsedUrl || urlValue ? 25 : 0,
    brand: brandAvailable ? 25 : 0,
    threat: 0,
    community: 0,
    coverage: 0,
  };
  const totalWeight = weights.content + weights.url + weights.brand;
  const weightedScore =
    (pointsByCategory.content * weights.content + pointsByCategory.url * weights.url + pointsByCategory.brand * weights.brand) /
    Math.max(totalWeight, 1);
  const score = Math.max(0, Math.min(100, Math.round(weightedScore)));
  const band = riskBand(score);
  const confidence = Math.min(
    0.88,
    0.62 + (parsedUrl ? 0.12 : 0) + (companyName ? 0.06 : 0) + (text.length >= 80 ? 0.06 : 0),
  );
  const dataCoverage = Math.round(totalWeight);
  const signalWeights: Record<string, number> = {
    content: Number((weights.content / Math.max(totalWeight, 1)).toFixed(2)),
    url: Number((weights.url / Math.max(totalWeight, 1)).toFixed(2)),
    brand: Number((weights.brand / Math.max(totalWeight, 1)).toFixed(2)),
    threat: 0,
    community: 0,
  };
  const unavailableSignals = [
    ...(!parsedUrl && !urlValue ? ['URL syntax review'] : []),
    ...(!brandAvailable ? ['Brand/contact consistency'] : []),
    'Threat-intelligence feeds',
    'Community and complaint history',
    'Company registry confirmation',
  ];
  const evidenceSummary = findings
    .filter((finding) => finding.indicator.status === 'suspicious' || finding.indicator.status === 'verified_inconsistency')
    .map((finding) => finding.indicator.name);

  const risk: AnalysisResult['risk'] = {
    score,
    category: band,
    inconclusive: text.length < 20 && !urlValue,
    summary: summaryFor(score),
    evidence_summary: evidenceSummary,
    recommended_actions: [
      'Do not pay an advance fee or share OTPs, passwords or full card details.',
      'Open the organisation’s official website yourself instead of using links from the message.',
      'Use the signed-in full scan for registry, threat and community checks when available.',
    ],
    confidence,
    uncertainty: Number((1 - confidence).toFixed(2)),
    data_coverage: dataCoverage / 100,
    weights_version: 'public-quick-scan-v1',
    signal_weights: signalWeights,
    unavailable_signals: unavailableSignals,
    component_scores: {
      content: Math.max(0, Math.min(100, pointsByCategory.content)),
      url: Math.max(0, Math.min(100, pointsByCategory.url)),
      brand: Math.max(0, Math.min(100, pointsByCategory.brand)),
      coverage: dataCoverage,
    },
  };

  return {
    id: `local-${hash(`${text}|${urlValue}|${companyName}|${category}`)}`,
    analysis_type: 'offer',
    offer_category: category,
    status: 'completed',
    user_id: 'public',
    created_at: observedAt,
    completed_at: observedAt,
    input_preview: (text || urlValue).slice(0, 240),
    extracted: {
      company_names: companyName ? [companyName] : [],
      job_titles: [],
      salary: null,
      recruiter_emails: emails,
      phone_numbers: phones,
      urls,
      payment_demands: paymentDemands,
      sensitive_data_requests: sensitiveRequests,
      locations: [],
    },
    model_predictions: [
      {
        model_name: 'offer_rule_fallback',
        model_version: 'public-quick-scan-v1',
        prediction: band,
        fraud_probability: score / 100,
        confidence,
        contributing_features: findings
          .filter((finding) => finding.points > 0)
          .map((finding) => ({ feature: finding.indicator.name, impact: Number((finding.points / 100).toFixed(2)) })),
        limitations: [
          'Rule-only assessment; no trained general-offer model was used.',
          'No external network lookup was performed in this browser scan.',
        ],
      },
    ],
    domain_intelligence: parsedUrl
      ? {
          url: parsedUrl.href,
          host: parsedUrl.hostname,
          protocol: parsedUrl.protocol,
          syntax_only: true,
          note: 'Only local URL syntax was inspected. No DNS, TLS, age or reputation lookup was performed.',
        }
      : { note: 'No source URL was supplied.' },
    company_intelligence: {
      claimed_name: companyName || null,
      note: 'No company registry was queried in the public quick scan.',
    },
    message_intelligence: {
      urgency_markers: contentRules
        .filter((rule) => rule.name === 'Urgency or scarcity pressure' && rule.pattern.test(text))
        .map((rule) => rule.name),
      tone: findings.some((finding) => finding.points >= 20) ? 'risk-patterns-present' : 'no-strong-pattern',
      note: 'Local text patterns only.',
    },
    historical_intelligence: { note: 'No historical or complaint data was queried.' },
    brand_intelligence: { note: 'No external brand registry or logo check was performed.' },
    threat_intelligence: { note: 'No threat-intelligence feed was queried.' },
    community_intelligence: { note: 'No community reports were queried.' },
    indicators: findings.map((finding) => finding.indicator),
    evidence_sources: [
      {
        name: 'Local text rules',
        status: 'succeeded',
        attempted_at: observedAt,
        observed_at: observedAt,
        detail: 'Pattern matching ran entirely in this browser; nothing was uploaded.',
      },
      {
        name: 'URL syntax checks',
        status: parsedUrl || urlValue ? 'succeeded' : 'not_attempted',
        attempted_at: observedAt,
        observed_at: observedAt,
        detail: 'Hostname and protocol checks were local only.',
      },
      {
        name: 'Registry, threat and community lookups',
        status: 'not_attempted',
        attempted_at: observedAt,
        observed_at: observedAt,
        detail: 'These checks require the signed-in full scan and are unavailable in the public build.',
      },
    ],
    missing_evidence: unavailableSignals,
    risk,
    technical_limitations: [
      'No trained general-offer model is used in the public quick scan.',
      'No external network lookups are performed; results depend only on the supplied text and URL.',
      'Local rules can miss novel scams and can flag legitimate wording.',
    ],
    sources_attempted: ['Local text rules', ...(parsedUrl || urlValue ? ['URL syntax checks'] : [])],
    sources_succeeded: ['Local text rules', ...(parsedUrl ? ['URL syntax checks'] : [])],
  };
}

export type FieldErrors = Record<string, string>;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function validateEmail(value: string): string | undefined {
  if (!value.trim()) return 'Email is required.';
  if (!EMAIL_RE.test(value.trim())) return 'Enter a valid email address.';
  return undefined;
}

export function validatePassword(value: string): string | undefined {
  if (!value) return 'Password is required.';
  if (value.length < 10) return 'Use at least 10 characters.';
  if (value.length > 128) return 'Use 128 characters or fewer.';
  if (!/[a-z]/.test(value) || !/[A-Z]/.test(value) || !/\d/.test(value)) {
    return 'Include uppercase, lowercase and a number.';
  }
  return undefined;
}

export function validateRegister(input: {
  email: string;
  password: string;
  full_name: string;
  consent_privacy: boolean;
  consent_terms: boolean;
}): FieldErrors {
  const errors: FieldErrors = {};
  const email = validateEmail(input.email);
  const password = validatePassword(input.password);
  if (email) errors.email = email;
  if (password) errors.password = password;
  if (input.full_name.trim().length < 2) errors.full_name = 'Enter your full name.';
  if (input.full_name.trim().length > 120) errors.full_name = 'Use 120 characters or fewer.';
  if (!input.consent_privacy) errors.consent_privacy = 'Please accept the privacy policy.';
  if (!input.consent_terms) errors.consent_terms = 'Please accept the terms.';
  return errors;
}

export function validateLogin(input: { email: string; password: string }): FieldErrors {
  const errors: FieldErrors = {};
  const email = validateEmail(input.email);
  if (email) errors.email = email;
  if (!input.password) errors.password = 'Password is required.';
  return errors;
}

export function validateJob(input: {
  text: string;
  company_name?: string;
  job_title?: string;
  recruiter_email?: string;
  source_url?: string;
}): FieldErrors {
  const errors: FieldErrors = {};
  const text = input.text.trim();
  if (text.length < 20) errors.text = 'Paste at least 20 characters of the recruitment text.';
  if (text.length > 200_000) errors.text = 'Job text is too long (200,000 character limit).';
  if (input.recruiter_email && validateEmail(input.recruiter_email)) {
    errors.recruiter_email = 'Enter a valid recruiter email.';
  }
  if (input.source_url && !/^https?:\/\/\S+\.\S+/.test(input.source_url)) {
    errors.source_url = 'Enter a valid http(s) URL.';
  }
  return errors;
}

export function validateOffer(input: {
  text: string;
  company_name?: string;
  source_url?: string;
}): FieldErrors {
  const errors: FieldErrors = {};
  const text = input.text.trim();
  if (text.length < 20) errors.text = 'Paste at least 20 characters of the offer.';
  if (text.length > 200_000) errors.text = 'Offer text is too long (200,000 character limit).';
  if (input.source_url && !/^https?:\/\/\S+\.\S+/.test(input.source_url)) {
    errors.source_url = 'Enter a valid http(s) URL.';
  }
  return errors;
}

export function validateMessage(input: {
  text: string;
  sender?: string;
}): FieldErrors {
  const errors: FieldErrors = {};
  const text = input.text.trim();
  if (text.length < 5) errors.text = 'Enter at least 5 characters.';
  if (text.length > 100_000) errors.text = 'Message is too long (100,000 character limit).';
  if ((input.sender?.length ?? 0) > 200) errors.sender = 'Sender is too long.';
  return errors;
}

export function validateUrl(input: { url: string }): FieldErrors {
  const errors: FieldErrors = {};
  if (!input.url.trim()) {
    errors.url = 'Enter a URL to analyse.';
  } else if (!/^https?:\/\/\S+\.\S+/.test(input.url.trim())) {
    errors.url = 'Enter a valid http(s) URL, e.g. https://example.com/job';
  } else if (input.url.length > 2048) {
    errors.url = 'URL is too long.';
  }
  return errors;
}

export function validateCompany(input: { company_name: string; website_url?: string }): FieldErrors {
  const errors: FieldErrors = {};
  if (input.company_name.trim().length < 2) errors.company_name = 'Enter a company name.';
  if (input.company_name.trim().length > 200) errors.company_name = 'Company name is too long.';
  if (input.website_url && !/^https?:\/\/\S+\.\S+/.test(input.website_url)) {
    errors.website_url = 'Enter a valid http(s) URL.';
  }
  return errors;
}

export function validateMonitoring(input: {
  name: string;
  company_names: string[];
  job_titles: string[];
  source_urls: string[];
  keywords: string[];
}): FieldErrors {
  const errors: FieldErrors = {};
  if (input.name.trim().length < 2) errors.name = 'Give this monitor a name (2+ characters).';
  if (input.name.trim().length > 120) errors.name = 'Name is too long.';
  if (!input.company_names.length && !input.job_titles.length && !input.keywords.length && !input.source_urls.length) {
    errors.targets = 'Add at least one company, job title, keyword or source URL.';
  }
  if (input.source_urls.some((url) => !/^https?:\/\/\S+\.\S+/.test(url))) {
    errors.source_urls = 'One or more source URLs are invalid.';
  }
  return errors;
}

export function validateFeedback(input: { details: string }): FieldErrors {
  const errors: FieldErrors = {};
  if (input.details.trim().length < 10) errors.details = 'Describe the issue in at least 10 characters.';
  if (input.details.length > 5000) errors.details = 'Use 5,000 characters or fewer.';
  return errors;
}

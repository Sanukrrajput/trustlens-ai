import { createPageExtractor } from './lib/extract.js';

const MAX_PAGE_CHARACTERS = 20000;
const SETTINGS_KEYS = ['apiBase', 'token', 'webBase'];

const elements = {
  analyse: document.getElementById('analyse'),
  pageLabel: document.getElementById('page-label'),
  result: document.getElementById('result'),
  riskCategory: document.getElementById('risk-category'),
  riskScore: document.getElementById('risk-score'),
  riskSummary: document.getElementById('risk-summary'),
  evidenceNote: document.getElementById('evidence-note'),
  indicators: document.getElementById('indicators'),
  openReport: document.getElementById('open-report'),
  error: document.getElementById('error'),
  apiBase: document.getElementById('api-base'),
  token: document.getElementById('token'),
  webBase: document.getElementById('web-base'),
  saveSettings: document.getElementById('save-settings'),
  clearSettings: document.getElementById('clear-settings'),
};

function showError(message) {
  elements.error.textContent = message;
  elements.error.hidden = false;
}

function clearError() {
  elements.error.textContent = '';
  elements.error.hidden = true;
}

function normaliseBase(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const parsed = new URL(raw);
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new Error('Only http(s) URLs are allowed.');
  }
  return parsed.href.replace(/\/$/, '');
}

function loadSettings() {
  return chrome.storage.local.get(SETTINGS_KEYS);
}

async function restoreSettings() {
  const settings = await loadSettings();
  elements.apiBase.value = settings.apiBase || '';
  elements.token.value = settings.token || '';
  elements.webBase.value = settings.webBase || '';
}

async function saveSettings() {
  clearError();
  try {
    const settings = {
      apiBase: normaliseBase(elements.apiBase.value),
      token: String(elements.token.value || '').trim(),
      webBase: normaliseBase(elements.webBase.value),
    };
    if (!settings.apiBase || !settings.token) {
      throw new Error('An API base URL and access token are required.');
    }
    await chrome.storage.local.set(settings);
    showNotice('Settings saved in this browser profile.');
  } catch (error) {
    showError(error instanceof Error ? error.message : String(error));
  }
}

function showNotice(message) {
  elements.pageLabel.textContent = message;
}

async function clearSettings() {
  await chrome.storage.local.remove(SETTINGS_KEYS);
  elements.apiBase.value = '';
  elements.token.value = '';
  elements.webBase.value = '';
  elements.result.hidden = true;
  clearError();
  showNotice('Saved settings removed.');
}

function renderResult(result, webBase) {
  const risk = result.risk || {};
  elements.riskCategory.textContent = String(risk.category || 'Assessment unavailable');
  elements.riskScore.textContent = `Uncalibrated risk score: ${Number(risk.score ?? 0).toFixed(0)} / 100`;
  elements.riskSummary.textContent = String(risk.summary || 'No summary was returned.');
  elements.evidenceNote.textContent = `Missing or unavailable checks: ${Array.isArray(result.missing_evidence) ? result.missing_evidence.length : 0}. A low score is not proof that an offer is legitimate.`;

  elements.indicators.replaceChildren();
  const indicators = Array.isArray(result.indicators) ? result.indicators.slice(0, 6) : [];
  if (!indicators.length) {
    const empty = document.createElement('li');
    empty.textContent = 'No indicators were returned by the service.';
    elements.indicators.append(empty);
  }
  for (const indicator of indicators) {
    const item = document.createElement('li');
    const name = document.createElement('strong');
    name.textContent = String(indicator.name || 'indicator');
    const description = document.createElement('span');
    description.textContent = ` — ${String(indicator.description || '')}`;
    item.append(name, description);
    elements.indicators.append(item);
  }

  if (webBase && result.id) {
    elements.openReport.href = `${webBase}/report/${encodeURIComponent(String(result.id))}`;
    elements.openReport.hidden = false;
  } else {
    elements.openReport.removeAttribute('href');
    elements.openReport.hidden = true;
  }
  elements.result.hidden = false;
}

async function analyseCurrentPage() {
  clearError();
  elements.result.hidden = true;
  elements.analyse.disabled = true;
  elements.analyse.textContent = 'Analysing…';

  try {
    const settings = await loadSettings();
    const apiBase = normaliseBase(settings.apiBase);
    const token = String(settings.token || '').trim();
    if (!apiBase || !token) {
      throw new Error('Save an API base URL and access token in Connection settings first.');
    }

    // The API origin is granted only after this explicit click, never at install.
    const apiOrigin = new URL(apiBase).origin;
    const granted = await chrome.permissions.request({ origins: [`${apiOrigin}/*`] });
    if (!granted) {
      throw new Error('Access to the configured API origin was not granted. No page data was sent.');
    }

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.id === undefined) {
      throw new Error('No active tab is available.');
    }
    const pageUrl = new URL(String(tab.url || ''));
    if (pageUrl.protocol !== 'https:' && pageUrl.protocol !== 'http:') {
      throw new Error('Only http(s) pages can be analysed. No data was sent.');
    }

    const injections = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: createPageExtractor(),
      args: [MAX_PAGE_CHARACTERS],
    });
    const snapshot = injections && injections[0] && injections[0].result;
    if (!snapshot || !snapshot.ok) {
      throw new Error(snapshot?.error || 'Page text could not be read.');
    }
    if (String(snapshot.text || '').trim().length < 20) {
      throw new Error('This page has too little text to assess (at least 20 characters are required). No data was sent.');
    }

    const response = await fetch(`${apiBase}/analysis/offer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        text: snapshot.text,
        source_url: String(snapshot.url || '').slice(0, 2048),
        offer_category: 'other',
        consent_external_lookups: false,
        client_request_id: crypto.randomUUID(),
      }),
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      throw new Error(`The API returned a non-JSON response (HTTP ${response.status}).`);
    }
    if (!response.ok) {
      const detail = payload.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg || 'invalid request').join('; ')
        : detail || `HTTP ${response.status}`;
      throw new Error(`The API rejected the request: ${message}`);
    }

    renderResult(payload, normaliseBase(settings.webBase));
    elements.pageLabel.textContent = `Checked ${snapshot.truncated ? 'the first 20,000 characters of ' : ''}the active page.`;
  } catch (error) {
    showError(error instanceof Error ? error.message : String(error));
  } finally {
    elements.analyse.disabled = false;
    elements.analyse.textContent = 'Analyse this page';
  }
}

elements.analyse.addEventListener('click', () => void analyseCurrentPage());
elements.saveSettings.addEventListener('click', () => void saveSettings());
elements.clearSettings.addEventListener('click', () => void clearSettings());

void restoreSettings();

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { createPageExtractor } from '../lib/extract.js';

const root = new URL('../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const manifest = JSON.parse(read('manifest.json'));
const popupSource = read('popup.js');
const extractorSource = read('lib/extract.js');

test('manifest requests only the minimum install-time permissions', () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual([...manifest.permissions].sort(), ['activeTab', 'scripting', 'storage']);
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.background, undefined);
  assert.equal(manifest.content_scripts, undefined);
  assert.deepEqual(manifest.optional_host_permissions, ['http://*/*', 'https://*/*']);
});

test('no background service worker, content script or silent monitoring hooks', () => {
  const sources = `${popupSource}\n${extractorSource}\n${JSON.stringify(manifest)}`;
  const forbidden = [
    'chrome.history',
    'chrome.webNavigation',
    'chrome.alarms',
    'chrome.cookies',
    'onUpdated',
    'onCreated',
    'onCommitted',
    'setInterval',
    'content_scripts',
    '"background"',
    'chrome.tabs.onActivated',
    'chrome.runtime.onInstalled',
  ];
  for (const token of forbidden) {
    assert.equal(sources.includes(token), false, `forbidden automatic hook present: ${token}`);
  }
  assert.match(popupSource, /addEventListener\('click'/);
});

test('analysis is sent only to the configured API after an explicit click', () => {
  assert.match(popupSource, /permissions\.request\(\{ origins/);
  assert.match(popupSource, /fetch\(`\$\{apiBase\}\/analysis\/offer`/);
  assert.match(popupSource, /consent_external_lookups: false/);
  assert.match(popupSource, /client_request_id: crypto\.randomUUID\(\)/);
  assert.doesNotMatch(popupSource, /innerHTML/);
});

test('extractor is self-contained so executeScript can serialise it', () => {
  const source = createPageExtractor().toString();
  assert.match(source, /maxCharacters/);
  assert.doesNotMatch(source, /MAX_PAGE_CHARACTERS/);
  assert.doesNotMatch(source, /createPageExtractor/);
});

test('extractor reads only the active page and caps untrusted text', () => {
  const originalDocument = globalThis.document;
  const originalLocation = globalThis.location;
  const longText = '  Offer   details '.repeat(5000);
  globalThis.document = {
    title: '  Special   offer  ',
    body: {
      innerText: longText,
      textContent: 'SCRIPT TEXT SHOULD NOT BE USED',
    },
    querySelector: (selector) => (
      selector === 'meta[name="description"]'
        ? { getAttribute: () => '  A   description  ' }
        : null
    ),
  };
  globalThis.location = { href: `https://example.com/${'a'.repeat(3000)}` };

  try {
    const snapshot = createPageExtractor()(2500);
    assert.equal(snapshot.ok, true);
    assert.equal(snapshot.title, 'Special offer');
    assert.equal(snapshot.description, 'A description');
    assert.equal(snapshot.text.length, 2500);
    assert.equal(snapshot.characterCount, 2500);
    assert.equal(snapshot.truncated, true);
    assert.equal(snapshot.url.length, 2048);
    assert.equal(snapshot.text.includes('SCRIPT TEXT'), false);
    assert.equal(snapshot.text.includes('\n'), false);
  } finally {
    globalThis.document = originalDocument;
    globalThis.location = originalLocation;
  }
});

test('extractor reports a missing page instead of inventing content', () => {
  const originalDocument = globalThis.document;
  globalThis.document = undefined;
  try {
    const snapshot = createPageExtractor()(20000);
    assert.equal(snapshot.ok, false);
    assert.match(snapshot.error, /not available/i);
  } finally {
    globalThis.document = originalDocument;
  }
});

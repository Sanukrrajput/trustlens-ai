/**
 * Self-contained page snapshot extractor.
 *
 * `chrome.scripting.executeScript({ func })` serialises the function with
 * `Function.prototype.toString()`, so the returned function must not close over
 * anything in this module. The character limit is supplied through `args`.
 *
 * Only the currently active page is read, and only after the user clicks
 * "Analyse this page". No history, cookies, form values, tabs or network bodies
 * are touched. All returned content is untrusted input.
 */
export function createPageExtractor() {
  return function extractPageSnapshot(maxCharacters) {
    const limit = Math.max(1000, Math.min(50000, Number(maxCharacters) || 20000));
    const doc = typeof document === 'undefined' ? null : document;
    const pageLocation = typeof location === 'undefined' ? null : location;

    if (!doc || !doc.body) {
      return { ok: false, error: 'Page content is not available in this tab.' };
    }

    const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
    const title = clean(doc.title).slice(0, 500);
    const descriptionTag = doc.querySelector ? doc.querySelector('meta[name="description"]') : null;
    const description = clean(descriptionTag && descriptionTag.getAttribute('content')).slice(0, 1000);
    const rawText = clean(doc.body.innerText || doc.body.textContent || '');
    const text = rawText.slice(0, limit);
    const href = clean(pageLocation && pageLocation.href).slice(0, 2048);

    return {
      ok: true,
      url: href,
      title: title,
      description: description,
      text: text,
      characterCount: text.length,
      truncated: rawText.length > text.length,
    };
  };
}

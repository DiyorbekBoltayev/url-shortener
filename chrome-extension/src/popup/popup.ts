// Popup entry point: reads the active tab, lets the user customise slug + tags,
// calls the API and renders the resulting short URL.

import { shorten, buildShortUrl } from '../lib/api.js';
import { getSettings } from '../lib/storage.js';

interface TabInfo {
  title: string;
  url: string;
}

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element: #${id}`);
  return el as T;
};

async function getActiveTab(): Promise<TabInfo> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return {
    title: tab?.title ?? '',
    url: tab?.url ?? '',
  };
}

function parseTags(raw: string): string[] {
  return raw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

function showError(message: string): void {
  const errBox = $('error');
  const msgEl = $('errorMessage');
  msgEl.textContent = message;
  errBox.hidden = false;
  $('result').hidden = true;
}

function clearError(): void {
  $('error').hidden = true;
}

function setLoading(loading: boolean): void {
  const btn = $<HTMLButtonElement>('shortenBtn');
  const spinner = btn.querySelector<HTMLElement>('.spinner');
  const label = btn.querySelector<HTMLElement>('.btn__label');
  btn.disabled = loading;
  if (spinner) spinner.hidden = !loading;
  if (label) label.textContent = loading ? 'Shortening...' : 'Shorten';
}

async function showResult(shortUrl: string, apiBase: string): Promise<void> {
  const result = $('result');
  const link = $<HTMLAnchorElement>('shortUrl');
  const dashboard = $<HTMLAnchorElement>('dashboardLink');
  link.textContent = shortUrl;
  link.href = shortUrl;
  dashboard.href = `${apiBase.replace(/\/+$/, '')}/dashboard`;
  result.hidden = false;
  clearError();
}

async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback using a temporary textarea.
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}

async function init(): Promise<void> {
  const tab = await getActiveTab();
  $('tabTitle').textContent = tab.title || '(untitled)';
  $('tabUrl').textContent = tab.url;

  const form = $<HTMLFormElement>('shortenForm');
  form.addEventListener('submit', async (evt) => {
    evt.preventDefault();
    clearError();

    const customSlug = $<HTMLInputElement>('customSlug').value.trim() || undefined;
    const tags = parseTags($<HTMLInputElement>('tags').value);

    if (!tab.url || !/^https?:\/\//i.test(tab.url)) {
      showError('Current tab has no shortenable URL.');
      return;
    }

    setLoading(true);
    try {
      const { apiBase } = await getSettings();
      const data = await shorten(tab.url, { customSlug, tags });
      const shortUrl = buildShortUrl(apiBase, data.short_code);
      await showResult(shortUrl, apiBase);
      await copyToClipboard(shortUrl).catch(() => undefined);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      showError(msg);
    } finally {
      setLoading(false);
    }
  });

  $('copyBtn').addEventListener('click', async () => {
    const link = $<HTMLAnchorElement>('shortUrl');
    if (link.href) {
      await copyToClipboard(link.textContent ?? link.href);
      const btn = $('copyBtn');
      const prev = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => {
        btn.textContent = prev ?? 'Copy';
      }, 1200);
    }
  });

  const openOptions = (evt: Event): void => {
    evt.preventDefault();
    chrome.runtime.openOptionsPage();
  };
  $('openOptions').addEventListener('click', openOptions);
  $('optionsLink').addEventListener('click', openOptions);
}

init().catch((err) => {
  showError(err instanceof Error ? err.message : String(err));
});

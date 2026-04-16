// Service worker (MV3): context menu for links, keyboard command for the
// active tab, and clipboard writes via an offscreen document (since SW has
// no DOM/navigator.clipboard).

import { shorten, buildShortUrl } from '../lib/api.js';
import { getSettings } from '../lib/storage.js';

const OFFSCREEN_URL = 'src/offscreen/offscreen.html';
const CONTEXT_MENU_ID = 'shorten-link';

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create(
    {
      id: CONTEXT_MENU_ID,
      title: 'Shorten this link',
      contexts: ['link', 'page', 'selection'],
    },
    () => {
      // Swallow the "duplicate id" error that occurs when re-installing.
      if (chrome.runtime.lastError) {
        // no-op
      }
    },
  );
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== CONTEXT_MENU_ID) return;
  const target =
    info.linkUrl ||
    (info.selectionText && /^https?:\/\//i.test(info.selectionText.trim())
      ? info.selectionText.trim()
      : undefined) ||
    tab?.url;
  if (!target) {
    await notify('URL Shortener', 'No link URL found to shorten.');
    return;
  }
  await shortenAndNotify(target);
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== 'shorten-current-tab') return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) {
    await notify('URL Shortener', 'No active tab URL.');
    return;
  }
  await shortenAndNotify(tab.url);
});

async function shortenAndNotify(longUrl: string): Promise<void> {
  try {
    if (!/^https?:\/\//i.test(longUrl)) {
      throw new Error('Only http(s) URLs can be shortened.');
    }
    const { apiBase } = await getSettings();
    const data = await shorten(longUrl);
    const shortUrl = buildShortUrl(apiBase, data.short_code);
    await copyViaOffscreen(shortUrl);
    await notify('Short URL copied', shortUrl);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Failed to shorten';
    await notify('URL Shortener error', msg);
  }
}

async function notify(title: string, message: string): Promise<void> {
  await chrome.notifications.create({
    type: 'basic',
    iconUrl: chrome.runtime.getURL('public/icons/icon-128.png'),
    title,
    message,
    priority: 1,
  });
}

// --- Offscreen clipboard helper -------------------------------------------

let creatingOffscreen: Promise<void> | null = null;

async function hasOffscreenDocument(): Promise<boolean> {
  // chrome.offscreen.hasDocument exists in Chrome 116+. Use getContexts as fallback.
  const runtimeAny = chrome.runtime as unknown as {
    getContexts?: (opts: {
      contextTypes: string[];
      documentUrls?: string[];
    }) => Promise<unknown[]>;
  };
  if (typeof runtimeAny.getContexts === 'function') {
    const contexts = await runtimeAny.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL(OFFSCREEN_URL)],
    });
    return contexts.length > 0;
  }
  return false;
}

async function ensureOffscreen(): Promise<void> {
  if (await hasOffscreenDocument()) return;
  if (creatingOffscreen) {
    await creatingOffscreen;
    return;
  }
  creatingOffscreen = chrome.offscreen
    .createDocument({
      url: OFFSCREEN_URL,
      reasons: ['CLIPBOARD' as chrome.offscreen.Reason],
      justification: 'Write shortened URL to clipboard',
    })
    .finally(() => {
      creatingOffscreen = null;
    });
  await creatingOffscreen;
}

async function copyViaOffscreen(text: string): Promise<void> {
  try {
    await ensureOffscreen();
    await chrome.runtime.sendMessage({ type: 'copy-to-clipboard', text });
  } catch (err) {
    // If offscreen clipboard fails we still have the notification.
    console.warn('Clipboard copy failed', err);
  }
}

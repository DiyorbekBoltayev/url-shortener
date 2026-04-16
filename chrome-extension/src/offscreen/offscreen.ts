// Offscreen document: receives messages from the service worker and writes
// to the clipboard via a hidden textarea + document.execCommand('copy').
// navigator.clipboard is not reliable in offscreen documents, so we use the
// legacy path which works without user activation in this context.

interface CopyMessage {
  type: 'copy-to-clipboard';
  text: string;
}

function isCopyMessage(msg: unknown): msg is CopyMessage {
  return (
    typeof msg === 'object' &&
    msg !== null &&
    (msg as { type?: unknown }).type === 'copy-to-clipboard' &&
    typeof (msg as { text?: unknown }).text === 'string'
  );
}

function copy(text: string): void {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.top = '0';
  ta.style.left = '0';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    document.execCommand('copy');
  } finally {
    document.body.removeChild(ta);
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!isCopyMessage(msg)) return false;
  try {
    copy(msg.text);
    sendResponse({ ok: true });
  } catch (err) {
    sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) });
  }
  return true;
});

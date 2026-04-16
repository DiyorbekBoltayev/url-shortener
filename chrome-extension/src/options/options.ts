// Options page: edit apiBase + apiKey, test connection to /api/v1/users/me.

import { getSettings, setSettings } from '../lib/storage.js';
import { getMe } from '../lib/api.js';

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element: #${id}`);
  return el as T;
};

function showStatus(message: string, kind: 'success' | 'error'): void {
  const status = $('status');
  status.textContent = message;
  status.className = `status status--${kind}`;
  status.hidden = false;
}

function clearStatus(): void {
  const status = $('status');
  status.hidden = true;
  status.textContent = '';
  status.className = 'status';
}

function normaliseBase(raw: string): string {
  return raw.trim().replace(/\/+$/, '');
}

async function hydrate(): Promise<void> {
  const { apiBase, apiKey } = await getSettings();
  $<HTMLInputElement>('apiBase').value = apiBase;
  $<HTMLInputElement>('apiKey').value = apiKey;
}

async function handleSave(evt: Event): Promise<void> {
  evt.preventDefault();
  clearStatus();
  const apiBase = normaliseBase($<HTMLInputElement>('apiBase').value);
  const apiKey = $<HTMLInputElement>('apiKey').value.trim();

  if (!apiBase || !apiKey) {
    showStatus('API base URL and key are required.', 'error');
    return;
  }

  try {
    await setSettings({ apiBase, apiKey });
    showStatus('Settings saved.', 'success');
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Failed to save';
    showStatus(msg, 'error');
  }
}

async function handleTest(): Promise<void> {
  clearStatus();
  const apiBase = normaliseBase($<HTMLInputElement>('apiBase').value);
  const apiKey = $<HTMLInputElement>('apiKey').value.trim();
  if (!apiBase || !apiKey) {
    showStatus('Enter API base URL and key before testing.', 'error');
    return;
  }

  const btn = $<HTMLButtonElement>('testBtn');
  btn.disabled = true;
  const prevLabel = btn.textContent;
  btn.textContent = 'Testing...';
  try {
    const me = await getMe(apiBase, apiKey);
    const label = me?.email ?? me?.name ?? me?.id ?? 'unknown user';
    showStatus(`Connected as ${label}.`, 'success');
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Connection failed';
    showStatus(msg, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = prevLabel ?? 'Test connection';
  }
}

function init(): void {
  hydrate().catch((err) => {
    showStatus(err instanceof Error ? err.message : String(err), 'error');
  });
  $<HTMLFormElement>('settingsForm').addEventListener('submit', handleSave);
  $('testBtn').addEventListener('click', handleTest);
}

init();

// Thin wrapper around chrome.storage.local for settings persistence.

export interface Settings {
  apiBase: string;
  apiKey: string;
}

const DEFAULT_SETTINGS: Settings = {
  apiBase: 'http://localhost',
  apiKey: '',
};

const STORAGE_KEYS: (keyof Settings)[] = ['apiBase', 'apiKey'];

export async function getSettings(): Promise<Settings> {
  const stored = await chrome.storage.local.get(STORAGE_KEYS);
  return {
    apiBase: (stored.apiBase as string) || DEFAULT_SETTINGS.apiBase,
    apiKey: (stored.apiKey as string) || DEFAULT_SETTINGS.apiKey,
  };
}

export async function setSettings(partial: Partial<Settings>): Promise<void> {
  await chrome.storage.local.set(partial);
}

export async function clearSettings(): Promise<void> {
  await chrome.storage.local.remove(STORAGE_KEYS);
}

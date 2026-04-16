// Fetch wrapper that injects the X-API-Key header from chrome.storage.local.
// No API key is ever hardcoded; it is always read from storage at call time.

import { getSettings } from './storage.js';

export interface ShortenOptions {
  customSlug?: string;
  tags?: string[];
}

export interface ShortenedUrl {
  short_code: string;
  long_url: string;
  short_url?: string;
  tags?: string[];
  created_at?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  name?: string;
}

interface ApiEnvelope<T> {
  success: boolean;
  data?: T;
  error?: { message?: string; code?: string };
}

function trimBase(base: string): string {
  return base.replace(/\/+$/, '');
}

async function apiFetch<T>(
  path: string,
  init: RequestInit & { apiBase: string; apiKey: string },
): Promise<T> {
  const { apiBase, apiKey, headers, ...rest } = init;
  const res = await fetch(`${trimBase(apiBase)}${path}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
      ...(headers ?? {}),
    },
  });

  let body: ApiEnvelope<T> | null = null;
  try {
    body = (await res.json()) as ApiEnvelope<T>;
  } catch {
    // fall through — body may legitimately be empty
  }

  if (!res.ok) {
    const msg = body?.error?.message ?? `API ${res.status} ${res.statusText}`;
    throw new Error(msg);
  }
  if (body && body.success === false) {
    throw new Error(body.error?.message ?? 'API request failed');
  }
  if (body && body.data !== undefined) return body.data;
  // Fall back to raw body for endpoints that do not wrap responses.
  return body as unknown as T;
}

export async function shorten(
  longUrl: string,
  opts: ShortenOptions = {},
): Promise<ShortenedUrl> {
  const { apiBase, apiKey } = await getSettings();
  if (!apiKey) {
    throw new Error('API key not set. Open extension options to configure.');
  }
  const body: Record<string, unknown> = { long_url: longUrl };
  if (opts.customSlug) body.custom_slug = opts.customSlug;
  if (opts.tags && opts.tags.length) body.tags = opts.tags;

  return apiFetch<ShortenedUrl>('/api/v1/urls', {
    apiBase,
    apiKey,
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getMe(apiBase: string, apiKey: string): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/v1/users/me', {
    apiBase,
    apiKey,
    method: 'GET',
  });
}

export function buildShortUrl(apiBase: string, shortCode: string): string {
  return `${trimBase(apiBase)}/${shortCode}`;
}

export type PixelKind =
  | 'fb'
  | 'ga4'
  | 'gtm'
  | 'linkedin'
  | 'tiktok'
  | 'pinterest'
  | 'twitter';

export interface PixelDto {
  id: string;
  workspace_id?: string;
  kind: PixelKind;
  pixel_id: string;
  name: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CreatePixelRequest {
  kind: PixelKind;
  pixel_id: string;
  name: string;
  is_active?: boolean;
}

export interface UpdatePixelRequest {
  kind?: PixelKind;
  pixel_id?: string;
  name?: string;
  is_active?: boolean;
}

export const PIXEL_KIND_LABELS: Record<PixelKind, string> = {
  fb: 'Facebook Pixel',
  ga4: 'Google Analytics 4',
  gtm: 'Google Tag Manager',
  linkedin: 'LinkedIn Insight',
  tiktok: 'TikTok Pixel',
  pinterest: 'Pinterest Tag',
  twitter: 'Twitter/X Pixel',
};

export const PIXEL_KIND_HELP: Record<PixelKind, string> = {
  fb: 'Find your FB Pixel ID in Meta Events Manager → Data sources.',
  ga4: 'Your GA4 Measurement ID looks like "G-XXXXXXXXXX" (Admin → Data streams).',
  gtm: 'Your GTM container ID looks like "GTM-XXXXXX".',
  linkedin: 'Find your LinkedIn Insight Tag Partner ID in Campaign Manager → Account assets → Insight tag.',
  tiktok: 'TikTok Pixel ID is a 20-char hex string from TikTok Events Manager.',
  pinterest: 'Pinterest Tag ID is in Ads Manager → Conversions.',
  twitter: 'Your Twitter/X Pixel ID is in Twitter Ads → Tools → Events manager.',
};

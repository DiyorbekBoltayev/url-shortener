export interface GeoRoutingRule {
  country: string; // ISO-2
  url: string;
}

export interface DeviceRoutingRules {
  ios?: string | null;
  android?: string | null;
  desktop?: string | null;
}

export interface AbVariant {
  url: string;
  weight: number; // 0-100
}

export interface RoutingRules {
  ab?: AbVariant[] | null;
  device?: DeviceRoutingRules | null;
  geo?: GeoRoutingRule[] | null;
}

export type QRDots = 'square' | 'rounded' | 'extra-rounded';
export type QRCorners = 'square' | 'rounded' | 'extra-rounded';
export type QRFrame = 'none' | 'rounded' | 'square';

/**
 * Branded QR style — mirrors backend ``app.schemas.qr.QRStyle``.
 *
 * All fields optional — absent means "fall back to defaults" (black/white,
 * square dots, no frame).
 */
export interface QRStyle {
  fg?: string | null;
  bg?: string | null;
  logo_url?: string | null;
  frame?: QRFrame | null;
  dots?: QRDots | null;
  corners?: QRCorners | null;
  eye_color?: string | null;
}

export type SafetyStatus = 'unchecked' | 'ok' | 'warn' | 'block';

export interface UrlDto {
  id: string;
  short_code: string;
  long_url: string;
  title: string | null;
  domain_id: string | null;
  click_count: number;
  last_clicked_at: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  max_clicks: number | null;
  tags?: string[] | null;
  folder_id?: string | null;
  routing_rules?: RoutingRules | null;
  qr_style?: QRStyle | null;
  preview_enabled: boolean;
  og_title?: string;
  og_description?: string;
  og_image_url?: string;
  favicon_url?: string;
  safety_status: SafetyStatus;
  safety_reason?: string;
}

export interface CreateUrlRequest {
  long_url: string;
  custom_slug?: string;
  title?: string;
  domain_id?: string;
  expires_at?: string;
  password?: string;
  tags?: string[];
  max_clicks?: number;
  folder_id?: string | null;
  routing_rules?: RoutingRules | null;
  qr_style?: QRStyle | null;
  preview_enabled?: boolean;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_term?: string;
  utm_content?: string;
}

export interface UpdateUrlRequest {
  /** Backend accepts `long_url` in URLUpdate (post RV6 alignment). */
  long_url?: string;
  title?: string;
  is_active?: boolean;
  expires_at?: string | null;
  tags?: string[];
  folder_id?: string | null;
  routing_rules?: RoutingRules | null;
  qr_style?: QRStyle | null;
  preview_enabled?: boolean;
}

export interface DomainDto {
  id: string;
  domain: string;
  is_verified: boolean;
  ssl_status: string;
  verified_at: string | null;
  dns_token: string;
  created_at: string;
}

export interface ApiKeyDto {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
  is_active?: boolean;
  /** Only present on creation response — shown to user once. */
  key?: string;
}

export interface WebhookDto {
  id: string;
  url: string;
  events: string[];
  is_active: boolean;
  secret_preview?: string;
  last_triggered?: string | null;
  failure_count?: number;
  created_at: string;
}

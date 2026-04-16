export interface TimeseriesPoint {
  t: string;   // ISO 8601
  clicks: number;
}

export interface TimeseriesResponse {
  points: TimeseriesPoint[];
  granularity: 'hour' | 'day';
}

export interface GeoBreakdown {
  country: string;
  country_code: string;
  clicks: number;
}

export interface ReferrerBreakdown {
  referer: string;
  clicks: number;
}

export interface DeviceBreakdown {
  device: 'desktop' | 'mobile' | 'tablet' | 'bot' | 'unknown';
  clicks: number;
}

export interface TopLink {
  id: string;
  short_code: string;
  long_url: string;
  title: string | null;
  clicks: number;
}

export interface OverviewStats {
  total_urls?: number;
  total_links: number;
  total_clicks: number;
  clicks_this_week: number;
  clicks_last_7d?: number;
  active_links: number;
  avg_ctr?: number;
  top_links?: TopLink[];
  top_referrers?: ReferrerBreakdown[];
  weekly_timeseries?: TimeseriesPoint[];
}

export type AnalyticsRange = '24h' | '7d' | '30d' | '90d';

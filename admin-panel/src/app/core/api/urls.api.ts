import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiService } from './api.service';
import {
  CreateUrlRequest,
  QRStyle,
  UpdateUrlRequest,
  UrlDto,
} from '../models/url.model';
import { PagedResult, PagingParams } from '../models/api-response.model';

/** Options accepted by :meth:`qrUrl` for inline preview overrides. */
export interface QrPreviewOptions {
  size?: number;
  fmt?: 'png' | 'svg';
  fg?: string;
  bg?: string;
  logo_url?: string;
  frame?: 'none' | 'rounded' | 'square';
  dots?: 'square' | 'rounded' | 'extra-rounded';
  corners?: 'square' | 'rounded' | 'extra-rounded';
  eye_color?: string;
}

@Injectable({ providedIn: 'root' })
export class UrlsApi {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  list(
    paging: PagingParams & { folder_id?: string | null },
  ): Observable<PagedResult<UrlDto>> {
    return this.api.getPaged<UrlDto>('/v1/urls', paging);
  }

  get(id: string): Observable<UrlDto> {
    return this.api.get<UrlDto>(`/v1/urls/${id}`);
  }

  create(req: CreateUrlRequest): Observable<UrlDto> {
    return this.api.post<UrlDto, CreateUrlRequest>('/v1/urls', req);
  }

  update(id: string, req: UpdateUrlRequest): Observable<UrlDto> {
    return this.api.patch<UrlDto, UpdateUrlRequest>(`/v1/urls/${id}`, req);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/urls/${id}`);
  }

  /** Anonymous/public short-link creation (landing page). */
  shortenPublic(longUrl: string): Observable<{ short_code: string; short_url: string }> {
    return this.api.post<{ short_code: string; short_url: string }>('/v1/shorten', { long_url: longUrl });
  }

  /** Check whether a custom alias is available. */
  checkAlias(alias: string): Observable<{ available: boolean }> {
    return this.api.get<{ available: boolean }>('/v1/urls/alias-check', { alias });
  }

  /** Persist a branded QR style as the per-URL default. */
  saveQrStyle(id: string, style: QRStyle): Observable<QRStyle> {
    return this.api.post<QRStyle, QRStyle>(`/v1/urls/${id}/qr-style`, style);
  }

  /**
   * Build the full `/qr` URL (including the ``/api`` prefix) for binding to
   * ``<img [src]>`` / ``<a [href]>``. Bypasses the HttpClient interceptor
   * because ``<img>`` requests go through the browser directly.
   *
   * Auth note: the backend ``GET /qr`` requires ``urls:read`` — direct
   * ``<img>`` binding will therefore only work when the API is under the
   * same origin with a cookie session or when a reverse proxy rewrites
   * the request. The :meth:`qrBlob` helper is preferred for authenticated
   * fetches inside the admin panel.
   */
  qrUrl(id: string, opts: QrPreviewOptions = {}): string {
    const base = (environment.apiBaseUrl ?? '').replace(/\/$/, '');
    const qs = qrQueryString(opts);
    return `${base}/v1/urls/${id}/qr${qs ? `?${qs}` : ''}`;
  }

  /** Fetch the styled QR as a Blob (authenticated — honours interceptors). */
  qrBlob(id: string, opts: QrPreviewOptions = {}): Observable<Blob> {
    const qs = qrQueryString(opts);
    const path = `/v1/urls/${id}/qr${qs ? `?${qs}` : ''}`;
    return this.http.get(path, { responseType: 'blob' });
  }
}

function qrQueryString(opts: QrPreviewOptions): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(opts)) {
    if (v === undefined || v === null || v === '') continue;
    params.set(k, String(v));
  }
  return params.toString();
}

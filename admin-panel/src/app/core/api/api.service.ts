import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import {
  ApiResponse,
  ApiSuccess,
  ApiMeta,
  PagedResult,
  PagingParams,
} from '../models/api-response.model';

/**
 * Thin HttpClient wrapper that strips the `{ success, data, meta }` envelope
 * (see INTEGRATION_CONTRACT §7) and throws on `success: false`.
 *
 * All paths are relative; the `apiBaseInterceptor` prepends `environment.apiBaseUrl`.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  /** GET returning a single entity or object. */
  get<T>(path: string, params?: Record<string, string | number | boolean | undefined | null>): Observable<T> {
    return this.http
      .get<ApiResponse<T>>(path, { params: toHttpParams(params) })
      .pipe(map((r) => unwrap(r)));
  }

  /** GET returning a paged collection. */
  getPaged<T>(path: string, paging: PagingParams = {}): Observable<PagedResult<T>> {
    return this.http
      .get<ApiResponse<T[]>>(path, { params: toHttpParams(paging as Record<string, unknown>) })
      .pipe(
        map((r) => {
          const body = assertSuccess(r);
          const meta: ApiMeta = body.meta ?? {};
          return {
            items: body.data,
            page: Number(meta['page'] ?? paging.page ?? 1),
            per_page: Number(meta['per_page'] ?? paging.per_page ?? body.data.length),
            total: Number(meta['total'] ?? body.data.length),
          } satisfies PagedResult<T>;
        }),
      );
  }

  post<T, B = unknown>(path: string, body?: B): Observable<T> {
    return this.http.post<ApiResponse<T>>(path, body ?? {}).pipe(map((r) => unwrap(r)));
  }

  put<T, B = unknown>(path: string, body?: B): Observable<T> {
    return this.http.put<ApiResponse<T>>(path, body ?? {}).pipe(map((r) => unwrap(r)));
  }

  patch<T, B = unknown>(path: string, body?: B): Observable<T> {
    return this.http.patch<ApiResponse<T>>(path, body ?? {}).pipe(map((r) => unwrap(r)));
  }

  delete<T = void>(path: string): Observable<T> {
    return this.http.delete<ApiResponse<T> | null>(path).pipe(
      map((r) => (r == null ? (null as unknown as T) : unwrap(r))),
    );
  }
}

/** Exported helper so callers outside ApiService can unwrap raw HttpClient responses consistently. */
export function unwrapApi<T>(r: ApiResponse<T>): T {
  return assertSuccess(r).data;
}

function toHttpParams(o?: Record<string, unknown> | undefined | null): HttpParams {
  let p = new HttpParams();
  if (!o) return p;
  for (const [k, v] of Object.entries(o)) {
    if (v === undefined || v === null || v === '') continue;
    p = p.set(k, String(v));
  }
  return p;
}

function unwrap<T>(r: ApiResponse<T>): T {
  return assertSuccess(r).data;
}

function assertSuccess<T>(r: ApiResponse<T>): ApiSuccess<T> {
  if (r && r.success === true) return r;
  const err = (r as { error?: { message?: string } })?.error;
  throw new Error(err?.message ?? 'API request failed');
}

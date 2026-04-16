/**
 * Response envelope from the backend — see INTEGRATION_CONTRACT §7.
 *
 *   { "success": true,  "data": ..., "meta": { "page", "per_page", "total" } }
 *   { "success": false, "error": { "code", "message", "retry_after" } }
 */
export interface ApiMeta {
  page?: number;
  per_page?: number;
  total?: number;
  // allow additional server-side meta (e.g. cursor) without breaking clients
  [k: string]: unknown;
}

export interface ApiError {
  code: string;
  message: string;
  retry_after?: number;
  /** per-field validation details (optional) */
  fields?: Record<string, string[]>;
}

export interface ApiSuccess<T> {
  success: true;
  data: T;
  meta?: ApiMeta;
}

export interface ApiFailure {
  success: false;
  error: ApiError;
}

export type ApiResponse<T> = ApiSuccess<T> | ApiFailure;

/** Offset/limit paging request params (see HLA §7). */
export interface PagingParams {
  page?: number;
  per_page?: number;
  /** generic search string — optional, each endpoint interprets */
  q?: string;
  sort?: string;
}

/** Paged listing result (unwrapped — ApiService strips the envelope). */
export interface PagedResult<T> {
  items: T[];
  page: number;
  per_page: number;
  total: number;
}

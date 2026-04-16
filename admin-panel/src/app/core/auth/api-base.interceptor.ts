import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../../environments/environment';

/**
 * Prepend `environment.apiBaseUrl` to all relative URLs. Absolute URLs
 * (`http://`, `https://`) pass through unchanged — useful for one-off
 * requests to e.g. short-link preview endpoints.
 */
// Paths that bypass the `/api` prefix because they are static assets served
// by the SPA's own nginx (translation JSON, runtime config, etc.).
const STATIC_PREFIXES = ['/assets/', '/public/'];

export const apiBaseInterceptor: HttpInterceptorFn = (req, next) => {
  if (/^https?:\/\//i.test(req.url)) return next(req);
  if (STATIC_PREFIXES.some((p) => req.url.startsWith(p))) return next(req);
  const base = environment.apiBaseUrl.replace(/\/+$/, '');
  const path = req.url.startsWith('/') ? req.url : `/${req.url}`;
  return next(req.clone({ url: `${base}${path}` }));
};

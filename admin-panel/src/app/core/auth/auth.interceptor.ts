import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

const ANON_PATHS = ['/auth/login', '/auth/register', '/auth/refresh', '/v1/shorten'];

function isAnonymous(url: string): boolean {
  return ANON_PATHS.some((p) => url.includes(p));
}

function addBearer<T>(req: HttpRequest<T>, token: string): HttpRequest<T> {
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

/**
 * Attaches `Authorization: Bearer <access>` and retries once on 401 by
 * calling `AuthService.refresh()` (single-flight inside the service).
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.accessToken();
  const outgoing = token && !isAnonymous(req.url) ? addBearer(req, token) : req;

  return next(outgoing).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status !== 401 || isAnonymous(req.url)) {
        return throwError(() => err);
      }
      return auth.refresh().pipe(
        switchMap((fresh) => next(addBearer(req, fresh))),
        catchError((refreshErr) => {
          auth.logout();
          return throwError(() => refreshErr);
        }),
      );
    }),
  );
};

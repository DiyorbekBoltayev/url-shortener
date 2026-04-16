import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';

/** Surfaces backend errors as PrimeNG toasts (5xx, 403, 429). */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(MessageService, { optional: true });
  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const body = (err.error ?? {}) as { error?: { message?: string; code?: string; retry_after?: number } };
      const serverMsg = body.error?.message;

      if (err.status === 0) {
        toast?.add({ severity: 'error', summary: 'Network', detail: 'Could not reach server.' });
      } else if (err.status >= 500) {
        toast?.add({ severity: 'error', summary: 'Server error', detail: serverMsg ?? err.message });
      } else if (err.status === 403) {
        toast?.add({ severity: 'warn', summary: 'Forbidden', detail: serverMsg ?? 'Access denied.' });
      } else if (err.status === 429) {
        const retry = body.error?.retry_after;
        toast?.add({
          severity: 'warn',
          summary: 'Rate limit',
          detail: retry ? `Try again in ${retry}s.` : (serverMsg ?? 'Rate limit exceeded.'),
        });
      }
      // 400/404/422 handled at component level
      return throwError(() => err);
    }),
  );
};

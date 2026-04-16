import { CanMatchFn, Router, UrlTree } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';

/**
 * `CanMatch` runs before the lazy chunk is downloaded — unauthenticated
 * users never pay for the dashboard bundle.
 *
 * Note: on a hard reload we also call `AuthService.bootstrap()` in
 * AppComponent, which may asynchronously restore a session. If the guard
 * fires before bootstrap completes, the user is redirected to /login; the
 * canonical "deep link after login" handling is up to the login page
 * (read `redirect` query param). For v1 the hard redirect is acceptable.
 */
export const authGuard: CanMatchFn = (): boolean | UrlTree => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isAuthenticated()) return true;
  return router.createUrlTree(['/login']);
};

/** Opposite — for routes that should not be visible to authed users (login/register). */
export const guestGuard: CanMatchFn = (): boolean | UrlTree => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.isAuthenticated() ? router.createUrlTree(['/dashboard']) : true;
};

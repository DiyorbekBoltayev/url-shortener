import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, catchError, filter, finalize, map, of, switchMap, take, tap, throwError } from 'rxjs';
import { AuthApi } from '../api/auth.api';
import {
  LoginRequest,
  RefreshResponse,
  RegisterRequest,
  TokenPair,
  User,
} from './models';

const REFRESH_KEY = 'rt';

/**
 * Auth state + token management (pure signals).
 *
 * Tradeoff: refresh token persisted in localStorage — any in-origin XSS can
 * steal it. Proper production uses an `httpOnly; Secure; SameSite=Strict`
 * cookie issued by the backend; swap-out is localized to this file plus
 * AuthApi (remove the `refresh_token` body field).
 *
 * The interceptor uses `auth.accessToken()`; the 401 refresh dance is
 * implemented here (single-flight via `BehaviorSubject` lock).
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly authApi = inject(AuthApi);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  /** In-memory only — lost on reload (bootstrap re-acquires via refresh token). */
  readonly accessToken = signal<string | null>(null);
  readonly user = signal<User | null>(null);
  readonly isAuthenticated = computed(() => this.accessToken() !== null);

  /** Single-flight refresh lock. */
  private isRefreshing = false;
  private refreshSubject = new BehaviorSubject<string | null>(null);

  /** Read the persisted refresh token (SSR-safe). */
  readRefreshToken(): string | null {
    try {
      return globalThis.localStorage?.getItem(REFRESH_KEY) ?? null;
    } catch {
      return null;
    }
  }

  private writeRefreshToken(token: string | null): void {
    try {
      if (token) globalThis.localStorage?.setItem(REFRESH_KEY, token);
      else globalThis.localStorage?.removeItem(REFRESH_KEY);
    } catch {
      /* ignore — storage disabled */
    }
  }

  /** Called once from AppComponent.ngOnInit to revive a session on page load. */
  bootstrap(): void {
    const rt = this.readRefreshToken();
    if (!rt) return;
    this.refresh()
      .pipe(
        switchMap(() => this.authApi.me()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (u) => this.user.set(u),
        error: () => this.clearSession(),
      });
  }

  login(req: LoginRequest): Observable<User> {
    return this.authApi.login(req).pipe(
      tap((pair) => this.applyTokenPair(pair)),
      map((pair: TokenPair) => pair.user),
    );
  }

  register(req: RegisterRequest): Observable<User> {
    return this.authApi.register(req).pipe(
      tap((pair) => this.applyTokenPair(pair)),
      map((pair: TokenPair) => pair.user),
    );
  }

  /**
   * Single-flight refresh.
   *  - first caller triggers POST /auth/refresh
   *  - concurrent callers block on `refreshSubject` until it resolves
   *  - on success: updates `accessToken()` + localStorage refresh
   *  - on failure: queued callers are rejected (subject.error) and the
   *    subject is replaced so the next cycle starts clean.
   */
  refresh(): Observable<string> {
    if (this.isRefreshing) {
      return this.refreshSubject.pipe(
        filter((t): t is string => t !== null),
        take(1),
      );
    }
    const rt = this.readRefreshToken();
    if (!rt) {
      this.clearSession();
      return throwError(() => new Error('No refresh token'));
    }
    this.isRefreshing = true;
    this.refreshSubject = new BehaviorSubject<string | null>(null);
    return this.authApi.refresh(rt).pipe(
      switchMap((d: RefreshResponse) => {
        this.accessToken.set(d.access_token);
        this.writeRefreshToken(d.refresh_token);
        this.refreshSubject.next(d.access_token);
        return of(d.access_token);
      }),
      catchError((err) => {
        // Wake up any queued callers with the error so they don't hang forever.
        this.refreshSubject.error(err);
        return throwError(() => err);
      }),
      finalize(() => {
        this.isRefreshing = false;
      }),
    );
  }

  /**
   * Apply a new access token from the workspace-switch endpoint — the
   * refresh token is unchanged (same user, different active workspace).
   */
  applySwitchedAccessToken(accessToken: string): void {
    this.accessToken.set(accessToken);
  }

  logout(): void {
    // Best-effort backend revocation — don't await.
    if (this.accessToken()) {
      this.authApi
        .logout()
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({ next: () => void 0, error: () => void 0 });
    }
    this.clearSession();
    this.router.navigateByUrl('/login');
  }

  private applyTokenPair(pair: TokenPair): void {
    this.accessToken.set(pair.tokens.access_token);
    this.writeRefreshToken(pair.tokens.refresh_token);
    this.user.set(pair.user);
  }

  private clearSession(): void {
    this.accessToken.set(null);
    this.user.set(null);
    this.writeRefreshToken(null);
  }
}

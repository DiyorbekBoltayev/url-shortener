import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  LoginRequest,
  RefreshResponse,
  RegisterRequest,
  TokenPair,
  User,
} from '../auth/models';

@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly api = inject(ApiService);

  login(req: LoginRequest): Observable<TokenPair> {
    return this.api.post<TokenPair>('/v1/auth/login', req);
  }

  register(req: RegisterRequest): Observable<TokenPair> {
    return this.api.post<TokenPair>('/v1/auth/register', req);
  }

  refresh(refreshToken: string): Observable<RefreshResponse> {
    return this.api.post<RefreshResponse>('/v1/auth/refresh', { refresh_token: refreshToken });
  }

  logout(): Observable<void> {
    return this.api.post<void>('/v1/auth/logout');
  }

  me(): Observable<User> {
    return this.api.get<User>('/v1/users/me');
  }
}

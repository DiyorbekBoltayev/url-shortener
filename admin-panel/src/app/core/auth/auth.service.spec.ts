import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let svc: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    svc = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('starts unauthenticated', () => {
    expect(svc.isAuthenticated()).toBe(false);
    expect(svc.accessToken()).toBeNull();
  });

  it('login sets token and user', (done) => {
    svc.login({ email: 'a@b.c', password: 'pw' }).subscribe(() => {
      expect(svc.isAuthenticated()).toBe(true);
      expect(svc.accessToken()).toBe('AAA');
      expect(localStorage.getItem('rt')).toBe('RRR');
      done();
    });
    const req = http.expectOne((r) => r.url.endsWith('/auth/login'));
    req.flush({
      success: true,
      data: {
        access_token: 'AAA',
        refresh_token: 'RRR',
        token_type: 'bearer',
        expires_in: 900,
        user: { id: '1', email: 'a@b.c', name: null, role: 'user', plan: 'free', created_at: '' },
      },
    });
  });

  it('logout clears tokens', (done) => {
    svc.login({ email: 'a@b.c', password: 'pw' }).subscribe(() => {
      svc.logout();
      // best-effort POST may or may not exist; drain whichever calls happened
      http.match(() => true).forEach((r) => r.flush({ success: true, data: null }));
      expect(svc.isAuthenticated()).toBe(false);
      expect(localStorage.getItem('rt')).toBeNull();
      done();
    });
    http.expectOne((r) => r.url.endsWith('/auth/login')).flush({
      success: true,
      data: {
        access_token: 'AAA',
        refresh_token: 'RRR',
        token_type: 'bearer',
        expires_in: 900,
        user: { id: '1', email: 'a@b.c', name: null, role: 'user', plan: 'free', created_at: '' },
      },
    });
  });
});

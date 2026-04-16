import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { HttpClient, provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding, withViewTransitions } from '@angular/router';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import { MessageService, ConfirmationService } from 'primeng/api';
import Aura from '@primeng/themes/aura';
import { provideTranslateService, TranslateLoader } from '@ngx-translate/core';
import { TranslateHttpLoader } from '@ngx-translate/http-loader';

import { routes } from './app.routes';
import { apiBaseInterceptor } from './core/auth/api-base.interceptor';
import { authInterceptor } from './core/auth/auth.interceptor';
import { errorInterceptor } from './core/auth/error.interceptor';

/** HttpLoader factory for lazy per-locale JSON fetch from /assets/i18n/<lang>.json. */
export function httpLoaderFactory(http: HttpClient): TranslateHttpLoader {
  return new TranslateHttpLoader(http, '/assets/i18n/', '.json');
}

/** Supported locales. Keep in sync with public/assets/i18n/<lang>.json files. */
export const SUPPORTED_LANGS = ['uz', 'ru', 'en'] as const;
export type SupportedLang = (typeof SUPPORTED_LANGS)[number];

/** Read persisted language from localStorage, falling back to Uzbek. */
export function getStoredLangOrDefault(): SupportedLang {
  try {
    const stored = globalThis.localStorage?.getItem('lang');
    if (stored && (SUPPORTED_LANGS as readonly string[]).includes(stored)) {
      return stored as SupportedLang;
    }
  } catch {
    /* ignore storage errors (SSR, private mode) */
  }
  return 'uz';
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding(), withViewTransitions()),
    provideHttpClient(
      withFetch(),
      withInterceptors([apiBaseInterceptor, authInterceptor, errorInterceptor]),
    ),
    provideAnimationsAsync(),
    providePrimeNG({
      theme: {
        preset: Aura,
        options: {
          prefix: 'p',
          darkModeSelector: '.dark',
          cssLayer: false,
        },
      },
      ripple: true,
    }),
    // ngx-translate v16 still exposes the legacy `defaultLanguage` option for
    // the fallback locale; the newer `fallbackLang` / `lang` names only shipped
    // in later minors. The initial language is set explicitly in main.ts via
    // `TranslateService.use(...)` once the app is bootstrapped.
    provideTranslateService({
      loader: {
        provide: TranslateLoader,
        useFactory: httpLoaderFactory,
        deps: [HttpClient],
      },
      defaultLanguage: 'uz',
    }),
    MessageService,
    ConfirmationService,
  ],
};

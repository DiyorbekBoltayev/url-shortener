import { bootstrapApplication } from '@angular/platform-browser';
import { TranslateService } from '@ngx-translate/core';
import { AppComponent } from './app/app.component';
import { appConfig, getStoredLangOrDefault } from './app/app.config';

const lang = getStoredLangOrDefault();

// Set <html lang="…"> ASAP so the first paint has the correct attribute.
try {
  document.documentElement.lang = lang;
} catch {
  /* ignore SSR / non-DOM environments */
}

bootstrapApplication(AppComponent, appConfig)
  .then((appRef) => {
    // Explicitly activate the stored locale after bootstrap. `provideTranslateService`
    // already sets it, but calling `.use(...)` here guarantees the HTTP loader
    // fetches the JSON and keeps us robust against future API changes.
    try {
      const translate = appRef.injector.get(TranslateService);
      translate.use(lang);
    } catch {
      /* non-fatal */
    }
  })
  .catch((err) =>
    // eslint-disable-next-line no-console
    console.error('[bootstrap]', err),
  );

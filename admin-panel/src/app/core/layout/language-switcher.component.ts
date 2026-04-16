import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ButtonModule } from 'primeng/button';
import { MenuModule } from 'primeng/menu';
import { TooltipModule } from 'primeng/tooltip';
import { MenuItem } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { SUPPORTED_LANGS, SupportedLang } from '../../app.config';

interface LangOption {
  code: SupportedLang;
  label: string;
  flag: string;
}

/**
 * Top-bar language switcher.
 *
 * Uses PrimeNG `p-menu` as a popup menu. Clicking an option:
 *   - calls `translate.use(lang)` so all pipes refresh
 *   - persists `lang` to localStorage (key: `lang`)
 *   - sets `document.documentElement.lang` for accessibility / SEO
 */
@Component({
  selector: 'app-language-switcher',
  standalone: true,
  imports: [ButtonModule, MenuModule, TooltipModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      pButton
      type="button"
      class="btn-ghost !px-2 flex items-center gap-1"
      (click)="menu.toggle($event)"
      aria-haspopup="true"
      [pTooltip]="'settings.language' | translate"
      tooltipPosition="bottom"
      [attr.aria-label]="'settings.language' | translate">
      <span class="text-base leading-none">{{ current().flag }}</span>
      <span class="hidden sm:inline text-xs font-medium uppercase">{{ current().code }}</span>
      <i class="pi pi-chevron-down text-[10px]"></i>
    </button>
    <p-menu #menu [popup]="true" [model]="items()" appendTo="body" />
  `,
})
export class LanguageSwitcherComponent {
  protected readonly translate = inject(TranslateService);

  /** Static flag+name metadata for the supported locales. */
  private readonly options: Record<SupportedLang, LangOption> = {
    uz: { code: 'uz', label: "O'zbekcha",  flag: '🇺🇿' },
    ru: { code: 'ru', label: 'Русский',    flag: '🇷🇺' },
    en: { code: 'en', label: 'English',    flag: '🇺🇸' },
  };

  /** Tracks the active language as a signal so the trigger re-renders on change. */
  private readonly active = signal<SupportedLang>(this.pickActive(this.translate.currentLang));

  constructor() {
    // Keep the local signal in sync when the language changes from elsewhere.
    this.translate.onLangChange.subscribe((e) => {
      this.active.set(this.pickActive(e.lang));
    });
  }

  readonly current = computed<LangOption>(() => this.options[this.active()]);

  readonly items = computed<MenuItem[]>(() =>
    (SUPPORTED_LANGS as readonly SupportedLang[]).map((code) => {
      const opt = this.options[code];
      return {
        label: `${opt.flag}  ${opt.label}`,
        command: () => this.setLang(code),
        styleClass: code === this.active() ? 'font-semibold' : '',
      };
    }),
  );

  private pickActive(lang: string | undefined): SupportedLang {
    if (lang && (SUPPORTED_LANGS as readonly string[]).includes(lang)) {
      return lang as SupportedLang;
    }
    return 'uz';
  }

  private setLang(lang: SupportedLang): void {
    this.translate.use(lang);
    try {
      globalThis.localStorage?.setItem('lang', lang);
    } catch {
      /* ignore storage errors */
    }
    try {
      document.documentElement.lang = lang;
    } catch {
      /* ignore SSR */
    }
    this.active.set(lang);
  }
}

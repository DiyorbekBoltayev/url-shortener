import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { MenuModule } from 'primeng/menu';
import { AvatarModule } from 'primeng/avatar';
import { TooltipModule } from 'primeng/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { filter } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '../auth/auth.service';
import { WorkspaceSwitcherComponent } from './workspace-switcher.component';
import { LanguageSwitcherComponent } from './language-switcher.component';

interface NavItem {
  /** i18n key (under the `nav` namespace) for the menu label. */
  labelKey: string;
  icon: string;
  route: string;
  exact?: boolean;
}

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    ButtonModule,
    MenuModule,
    AvatarModule,
    TooltipModule,
    TranslateModule,
    WorkspaceSwitcherComponent,
    LanguageSwitcherComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './main-layout.component.html',
})
export class MainLayoutComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly user = this.auth.user;
  readonly collapsed = signal(false);
  readonly mobileOpen = signal(false);

  /** Dark-mode toggle — persisted to localStorage. */
  readonly darkMode = signal<boolean>(
    (() => {
      try {
        return globalThis.localStorage?.getItem('theme') === 'dark';
      } catch {
        return false;
      }
    })(),
  );

  constructor() {
    // Keep the <html> class + localStorage in sync with the darkMode signal.
    effect(() => {
      const on = this.darkMode();
      try {
        document.documentElement.classList.toggle('dark', on);
        globalThis.localStorage?.setItem('theme', on ? 'dark' : 'light');
      } catch {
        /* ignore SSR / private-mode storage errors */
      }
    });
    // Auto-close mobile drawer on route change.
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.mobileOpen.set(false));
  }

  readonly nav: NavItem[] = [
    { labelKey: 'nav.overview', icon: 'pi pi-chart-line', route: '/dashboard',          exact: true },
    { labelKey: 'nav.links',    icon: 'pi pi-link',       route: '/dashboard/links' },
    { labelKey: 'nav.domains',  icon: 'pi pi-globe',      route: '/dashboard/domains' },
    { labelKey: 'nav.api_keys', icon: 'pi pi-key',        route: '/dashboard/api-keys' },
    { labelKey: 'nav.webhooks', icon: 'pi pi-send',       route: '/dashboard/webhooks' },
    { labelKey: 'nav.settings', icon: 'pi pi-cog',        route: '/dashboard/settings' },
  ];

  readonly initials = computed(() => {
    const u = this.user();
    if (!u) return '?';
    const src = u.full_name || u.email;
    const parts = src.split(/[\s@.]+/).filter(Boolean);
    return (parts[0]?.[0] ?? '').concat(parts[1]?.[0] ?? '').toUpperCase() || '?';
  });

  toggle(): void {
    this.collapsed.update((v) => !v);
  }

  toggleMobile(): void {
    this.mobileOpen.update((v) => !v);
  }

  toggleDark(): void {
    this.darkMode.update((v) => !v);
  }

  logout(): void {
    this.auth.logout();
  }
}

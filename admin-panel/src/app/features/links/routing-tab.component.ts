import {
  ChangeDetectionStrategy,
  Component,
  computed,
  forwardRef,
  input,
  signal,
} from '@angular/core';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { InputNumberModule } from 'primeng/inputnumber';
import { SelectModule } from 'primeng/select';
import { TabsModule } from 'primeng/tabs';
import { RoutingRules, AbVariant, GeoRoutingRule } from '../../core/models/url.model';

const COUNTRIES: { label: string; value: string }[] = [
  { label: 'United States (US)', value: 'US' },
  { label: 'United Kingdom (GB)', value: 'GB' },
  { label: 'Canada (CA)', value: 'CA' },
  { label: 'Germany (DE)', value: 'DE' },
  { label: 'France (FR)', value: 'FR' },
  { label: 'Spain (ES)', value: 'ES' },
  { label: 'Italy (IT)', value: 'IT' },
  { label: 'Brazil (BR)', value: 'BR' },
  { label: 'Mexico (MX)', value: 'MX' },
  { label: 'Japan (JP)', value: 'JP' },
  { label: 'China (CN)', value: 'CN' },
  { label: 'India (IN)', value: 'IN' },
  { label: 'Australia (AU)', value: 'AU' },
  { label: 'Netherlands (NL)', value: 'NL' },
  { label: 'Sweden (SE)', value: 'SE' },
  { label: 'Norway (NO)', value: 'NO' },
  { label: 'Denmark (DK)', value: 'DK' },
  { label: 'Poland (PL)', value: 'PL' },
  { label: 'Russia (RU)', value: 'RU' },
  { label: 'Turkey (TR)', value: 'TR' },
  { label: 'South Korea (KR)', value: 'KR' },
  { label: 'Singapore (SG)', value: 'SG' },
];

@Component({
  selector: 'app-routing-tab',
  standalone: true,
  imports: [
    FormsModule,
    ButtonModule,
    InputTextModule,
    InputNumberModule,
    SelectModule,
    TabsModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => RoutingTabComponent),
      multi: true,
    },
  ],
  template: `
    <p-tabs [value]="activeTab()" (valueChange)="activeTab.set($any($event))">
      <p-tablist>
        <p-tab value="geo"><i class="pi pi-globe"></i> Geo</p-tab>
        <p-tab value="device"><i class="pi pi-mobile"></i> Device</p-tab>
        <p-tab value="ab"><i class="pi pi-chart-pie"></i> A/B Split</p-tab>
      </p-tablist>

      <p-tabpanels>
        <!-- GEO -->
        <p-tabpanel value="geo">
          <p class="text-sm text-slate-500 mb-2">
            Route visitors by country (ISO-2). The default URL is used when no rule matches.
          </p>
          @for (row of geoRows(); track $index) {
            <div class="flex items-center gap-2 mb-2">
              <p-select
                [options]="countries"
                optionLabel="label"
                optionValue="value"
                [ngModel]="row.country"
                (ngModelChange)="updateGeo($index, 'country', $event)"
                placeholder="Country"
                styleClass="w-44" />
              <input pInputText class="flex-1" placeholder="https://..."
                     [ngModel]="row.url"
                     (ngModelChange)="updateGeo($index, 'url', $event)" />
              <button pButton type="button" class="p-button-sm p-button-text p-button-danger"
                      icon="pi pi-times" (click)="removeGeo($index)" aria-label="Remove row"></button>
            </div>
          }
          <button pButton type="button" class="p-button-sm" icon="pi pi-plus"
                  label="Add country rule" (click)="addGeo()"></button>
          <div class="mt-3 text-xs text-slate-500">
            <strong>Default URL</strong> (no match): the link's primary <em>long_url</em> is used.
          </div>
        </p-tabpanel>

        <!-- DEVICE -->
        <p-tabpanel value="device">
          <p class="text-sm text-slate-500 mb-2">
            Send users to different URLs based on their device. Leave empty to fall back to the
            primary URL.
          </p>
          <div class="grid grid-cols-1 gap-3">
            <div>
              <label class="form-label">iOS URL</label>
              <input pInputText class="w-full" placeholder="https://apps.apple.com/..."
                     [ngModel]="device().ios ?? ''"
                     (ngModelChange)="updateDevice('ios', $event)" />
            </div>
            <div>
              <label class="form-label">Android URL</label>
              <input pInputText class="w-full" placeholder="https://play.google.com/..."
                     [ngModel]="device().android ?? ''"
                     (ngModelChange)="updateDevice('android', $event)" />
            </div>
            <div>
              <label class="form-label">Desktop URL</label>
              <input pInputText class="w-full" placeholder="https://example.com/desktop"
                     [ngModel]="device().desktop ?? ''"
                     (ngModelChange)="updateDevice('desktop', $event)" />
            </div>
          </div>
        </p-tabpanel>

        <!-- A/B -->
        <p-tabpanel value="ab">
          <p class="text-sm text-slate-500 mb-2">
            Split traffic between multiple destinations. Weights must sum to 100.
          </p>
          @for (v of abVariants(); track $index) {
            <div class="flex items-center gap-2 mb-2">
              <input pInputText class="flex-1" placeholder="https://..."
                     [ngModel]="v.url"
                     (ngModelChange)="updateAb($index, 'url', $event)" />
              <p-inputNumber
                [ngModel]="v.weight"
                (ngModelChange)="updateAb($index, 'weight', $event ?? 0)"
                [min]="0" [max]="100" [suffix]="'%'" styleClass="w-24" inputStyleClass="w-full" />
              <button pButton type="button" class="p-button-sm p-button-text p-button-danger"
                      icon="pi pi-times" (click)="removeAb($index)" aria-label="Remove variant"></button>
            </div>
          }
          <div class="flex items-center gap-3 mt-1">
            <button pButton type="button" class="p-button-sm" icon="pi pi-plus"
                    label="Add variant" (click)="addAb()"></button>
            <span class="text-sm" [class.text-red-600]="weightSum() !== 100"
                  [class.text-green-600]="weightSum() === 100">
              Weights sum: {{ weightSum() }}%
            </span>
          </div>
        </p-tabpanel>
      </p-tabpanels>
    </p-tabs>
  `,
})
export class RoutingTabComponent implements ControlValueAccessor {
  readonly urlId = input<string | null>(null);

  readonly countries = COUNTRIES;
  readonly activeTab = signal<'geo' | 'device' | 'ab'>('geo');

  readonly geoRows = signal<GeoRoutingRule[]>([]);
  readonly device = signal<{ ios?: string | null; android?: string | null; desktop?: string | null }>({});
  readonly abVariants = signal<AbVariant[]>([]);

  readonly weightSum = computed(() =>
    this.abVariants().reduce((s, v) => s + (Number(v.weight) || 0), 0),
  );

  private onChange: (v: RoutingRules) => void = () => void 0;
  private onTouched: () => void = () => void 0;

  addGeo(): void {
    this.geoRows.update((l) => [...l, { country: '', url: '' }]);
    this.emit();
  }

  removeGeo(i: number): void {
    this.geoRows.update((l) => l.filter((_, idx) => idx !== i));
    this.emit();
  }

  updateGeo(i: number, key: 'country' | 'url', value: string): void {
    this.geoRows.update((l) => l.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)));
    this.emit();
  }

  updateDevice(key: 'ios' | 'android' | 'desktop', value: string): void {
    this.device.update((d) => ({ ...d, [key]: value || null }));
    this.emit();
  }

  addAb(): void {
    this.abVariants.update((l) => [...l, { url: '', weight: 0 }]);
    this.emit();
  }

  removeAb(i: number): void {
    this.abVariants.update((l) => l.filter((_, idx) => idx !== i));
    this.emit();
  }

  updateAb(i: number, key: 'url' | 'weight', value: string | number): void {
    this.abVariants.update((l) =>
      l.map((v, idx) => (idx === i ? { ...v, [key]: value } : v)),
    );
    this.emit();
  }

  private emit(): void {
    this.onChange(this.serialize());
    this.onTouched();
  }

  private serialize(): RoutingRules {
    const geo = this.geoRows().filter((r) => r.country && r.url);
    const d = this.device();
    const hasDevice = !!(d.ios || d.android || d.desktop);
    const ab = this.abVariants().filter((v) => v.url && v.weight > 0);
    return {
      geo: geo.length ? geo : null,
      device: hasDevice ? d : null,
      ab: ab.length ? ab : null,
    };
  }

  // --- CVA ---
  writeValue(v: RoutingRules | null): void {
    this.geoRows.set(v?.geo ?? []);
    this.device.set(v?.device ?? {});
    this.abVariants.set(v?.ab ?? []);
  }

  registerOnChange(fn: (v: RoutingRules) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(_: boolean): void {
    /* not implemented */
  }
}

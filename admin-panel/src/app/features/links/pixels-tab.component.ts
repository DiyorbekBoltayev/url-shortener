import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  inject,
  input,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MultiSelectModule } from 'primeng/multiselect';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { MessageService } from 'primeng/api';
import { firstValueFrom, forkJoin, of } from 'rxjs';
import { PixelsApi } from '../../core/api/pixels.api';
import { PixelDto, PIXEL_KIND_LABELS } from '../../core/models/pixel.model';

@Component({
  selector: 'app-pixels-tab',
  standalone: true,
  imports: [FormsModule, MultiSelectModule, ButtonModule, TagModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex flex-col gap-3">
      <p class="text-sm text-slate-500">
        Attach workspace pixels to this link. Each pixel fires on every click
        (via the redirect interstitial).
      </p>

      <p-multiSelect
        [options]="allPixels()"
        optionLabel="name"
        optionValue="id"
        [ngModel]="selectedIds()"
        (ngModelChange)="selectedIds.set($event)"
        placeholder="Select pixels…"
        styleClass="w-full"
        [showToggleAll]="true"
        [filter]="true"
        filterBy="name,kind,pixel_id" />

      @if (selectedIds().length > 0) {
        <div class="flex flex-wrap gap-1">
          @for (id of selectedIds(); track id) {
            @if (pixelById(id); as p) {
              <p-tag [value]="p.name + ' (' + kindLabel(p.kind) + ')'" />
            }
          }
        </div>
      } @else {
        <div class="text-xs text-slate-400 italic">No pixels attached.</div>
      }

      <div class="flex items-center justify-end gap-2">
        <button pButton type="button" class="btn-primary"
                [disabled]="!urlId() || saving()"
                [label]="saving() ? 'Saving…' : 'Save attachments'"
                (click)="save()"></button>
      </div>
    </div>
  `,
})
export class PixelsTabComponent implements OnInit {
  readonly urlId = input<string | null>(null);

  private readonly api = inject(PixelsApi);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly allPixels = signal<PixelDto[]>([]);
  readonly initialIds = signal<string[]>([]);
  readonly selectedIds = signal<string[]>([]);
  readonly saving = signal(false);

  kindLabel(k: PixelDto['kind']): string {
    return PIXEL_KIND_LABELS[k] ?? k;
  }

  pixelById(id: string): PixelDto | undefined {
    return this.allPixels().find((p) => p.id === id);
  }

  ngOnInit(): void {
    const id = this.urlId();
    forkJoin({
      all: this.api.list(),
      attached: id ? this.api.forUrl(id) : of<PixelDto[]>([]),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ all, attached }) => {
          this.allPixels.set(all);
          const ids = attached.map((p) => p.id);
          this.initialIds.set(ids);
          this.selectedIds.set(ids);
        },
        error: () => {
          this.allPixels.set([]);
        },
      });
  }

  async save(): Promise<void> {
    const id = this.urlId();
    if (!id) return;
    this.saving.set(true);
    const initial = new Set(this.initialIds());
    const now = new Set(this.selectedIds());
    const toAttach = [...now].filter((x) => !initial.has(x));
    const toDetach = [...initial].filter((x) => !now.has(x));
    try {
      if (toAttach.length) {
        await firstValueFrom(this.api.attach(id, toAttach));
      }
      for (const pid of toDetach) {
        await firstValueFrom(this.api.detach(id, pid));
      }
      this.initialIds.set([...now]);
      this.toast.add({
        severity: 'success',
        summary: 'Pixels saved',
        detail: `${toAttach.length} attached, ${toDetach.length} detached.`,
      });
    } catch (e) {
      this.toast.add({ severity: 'error', summary: 'Save failed', detail: (e as Error).message });
    } finally {
      this.saving.set(false);
    }
  }
}

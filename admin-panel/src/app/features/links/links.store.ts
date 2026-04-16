import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { UrlsApi } from '../../core/api/urls.api';
import { CreateUrlRequest, UpdateUrlRequest, UrlDto } from '../../core/models/url.model';

interface LinksFilter {
  page: number;
  per_page: number;
  q: string;
  sort: string;
  folder_id: string | null;
}

/**
 * Signal-based store for the links list. No ngrx boilerplate — pure signals
 * + async methods. Consumers use `items()`, `total()`, `loading()`,
 * `error()` reactively and call `load()`, `create()`, `remove()`.
 */
@Injectable({ providedIn: 'root' })
export class LinksStore {
  private readonly api = inject(UrlsApi);

  readonly items = signal<UrlDto[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly filter = signal<LinksFilter>({
    page: 1,
    per_page: 20,
    q: '',
    sort: '-created_at',
    folder_id: null,
  });

  readonly isEmpty = computed(() => !this.loading() && this.items().length === 0);
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.total() / this.filter().per_page)));

  setPage(page: number): void {
    this.filter.update((f) => ({ ...f, page }));
    void this.load();
  }

  setPerPage(per_page: number): void {
    this.filter.update((f) => ({ ...f, per_page, page: 1 }));
    void this.load();
  }

  setQuery(q: string): void {
    this.filter.update((f) => ({ ...f, q, page: 1 }));
    void this.load();
  }

  setSort(sort: string): void {
    this.filter.update((f) => ({ ...f, sort }));
    void this.load();
  }

  setFolder(folder_id: string | null): void {
    this.filter.update((f) => ({ ...f, folder_id, page: 1 }));
    void this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await firstValueFrom(this.api.list(this.filter()));
      this.items.set(res.items);
      this.total.set(res.total);
    } catch (e) {
      this.error.set((e as Error).message || 'Failed to load links');
      this.items.set([]);
      this.total.set(0);
    } finally {
      this.loading.set(false);
    }
  }

  async create(req: CreateUrlRequest): Promise<UrlDto> {
    const created = await firstValueFrom(this.api.create(req));
    this.items.update((l) => [created, ...l]);
    this.total.update((t) => t + 1);
    return created;
  }

  async update(id: string, req: UpdateUrlRequest): Promise<UrlDto> {
    const updated = await firstValueFrom(this.api.update(id, req));
    this.items.update((l) => l.map((x) => (x.id === id ? updated : x)));
    return updated;
  }

  async remove(id: string): Promise<void> {
    await firstValueFrom(this.api.delete(id));
    this.items.update((l) => l.filter((x) => x.id !== id));
    this.total.update((t) => Math.max(0, t - 1));
  }
}

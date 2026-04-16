import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { WebhookDto } from '../models/url.model';
import { PagedResult, PagingParams } from '../models/api-response.model';

@Injectable({ providedIn: 'root' })
export class WebhooksApi {
  private readonly api = inject(ApiService);

  list(paging: PagingParams = {}): Observable<PagedResult<WebhookDto>> {
    return this.api.getPaged<WebhookDto>('/v1/webhooks', paging);
  }

  create(req: { url: string; events: string[] }): Observable<WebhookDto> {
    return this.api.post<WebhookDto>('/v1/webhooks', req);
  }

  update(id: string, req: Partial<{ url: string; events: string[]; is_active: boolean }>): Observable<WebhookDto> {
    return this.api.patch<WebhookDto>(`/v1/webhooks/${id}`, req);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/webhooks/${id}`);
  }

  test(id: string): Observable<{ ok: boolean }> {
    return this.api.post<{ ok: boolean }>(`/v1/webhooks/${id}/test`);
  }
}

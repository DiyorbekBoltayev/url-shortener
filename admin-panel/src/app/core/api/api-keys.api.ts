import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { ApiKeyDto } from '../models/url.model';
import { PagedResult, PagingParams } from '../models/api-response.model';

@Injectable({ providedIn: 'root' })
export class ApiKeysApi {
  private readonly api = inject(ApiService);

  list(paging: PagingParams = {}): Observable<PagedResult<ApiKeyDto>> {
    return this.api.getPaged<ApiKeyDto>('/v1/api-keys', paging);
  }

  create(req: { name: string; scopes: string[]; expires_at?: string }): Observable<ApiKeyDto> {
    return this.api.post<ApiKeyDto>('/v1/api-keys', req);
  }

  revoke(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/api-keys/${id}`);
  }
}

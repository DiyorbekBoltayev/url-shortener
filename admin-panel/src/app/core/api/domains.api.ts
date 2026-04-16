import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { DomainDto } from '../models/url.model';
import { PagedResult, PagingParams } from '../models/api-response.model';

@Injectable({ providedIn: 'root' })
export class DomainsApi {
  private readonly api = inject(ApiService);

  list(paging: PagingParams = {}): Observable<PagedResult<DomainDto>> {
    return this.api.getPaged<DomainDto>('/v1/domains', paging);
  }

  create(domain: string): Observable<DomainDto> {
    return this.api.post<DomainDto>('/v1/domains', { domain });
  }

  verify(id: string): Observable<DomainDto> {
    return this.api.post<DomainDto>(`/v1/domains/${id}/verify`);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/domains/${id}`);
  }
}

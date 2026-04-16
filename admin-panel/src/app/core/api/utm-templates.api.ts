import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  CreateUtmTemplateRequest,
  UpdateUtmTemplateRequest,
  UtmTemplateDto,
} from '../models/utm-template.model';

@Injectable({ providedIn: 'root' })
export class UtmTemplatesApi {
  private readonly api = inject(ApiService);

  list(): Observable<UtmTemplateDto[]> {
    return this.api.get<UtmTemplateDto[]>('/v1/utm-templates');
  }

  create(req: CreateUtmTemplateRequest): Observable<UtmTemplateDto> {
    return this.api.post<UtmTemplateDto, CreateUtmTemplateRequest>('/v1/utm-templates', req);
  }

  update(id: string, req: UpdateUtmTemplateRequest): Observable<UtmTemplateDto> {
    return this.api.patch<UtmTemplateDto, UpdateUtmTemplateRequest>(
      `/v1/utm-templates/${id}`,
      req,
    );
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/utm-templates/${id}`);
  }
}

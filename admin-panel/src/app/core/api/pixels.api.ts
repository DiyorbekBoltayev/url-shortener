import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  CreatePixelRequest,
  PixelDto,
  UpdatePixelRequest,
} from '../models/pixel.model';

@Injectable({ providedIn: 'root' })
export class PixelsApi {
  private readonly api = inject(ApiService);

  list(): Observable<PixelDto[]> {
    return this.api.get<PixelDto[]>('/v1/pixels');
  }

  create(req: CreatePixelRequest): Observable<PixelDto> {
    return this.api.post<PixelDto, CreatePixelRequest>('/v1/pixels', req);
  }

  update(id: string, req: UpdatePixelRequest): Observable<PixelDto> {
    return this.api.patch<PixelDto, UpdatePixelRequest>(`/v1/pixels/${id}`, req);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/pixels/${id}`);
  }

  /** Attach one or more pixels to a URL. */
  attach(urlId: string, pixelIds: string[]): Observable<{ attached: number }> {
    return this.api.post<{ attached: number }>(`/v1/urls/${urlId}/pixels`, {
      pixel_ids: pixelIds,
    });
  }

  /** Detach a single pixel from a URL. */
  detach(urlId: string, pixelId: string): Observable<void> {
    return this.api.delete<void>(`/v1/urls/${urlId}/pixels/${pixelId}`);
  }

  /** Fetch the pixels currently attached to a URL. */
  forUrl(urlId: string): Observable<PixelDto[]> {
    return this.api.get<PixelDto[]>(`/v1/urls/${urlId}/pixels`);
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { ApiService, unwrapApi } from './api.service';
import type { ApiResponse } from '../models/api-response.model';
import {
  BulkJobDto,
  BulkPatchRequest,
  ColumnMap,
  ExportCsvRequest,
} from '../models/bulk-job.model';

@Injectable({ providedIn: 'root' })
export class BulkJobsApi {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  list(): Observable<BulkJobDto[]> {
    return this.api.get<BulkJobDto[]>('/v1/bulk-jobs');
  }

  get(id: string): Observable<BulkJobDto> {
    return this.api.get<BulkJobDto>(`/v1/bulk-jobs/${id}`);
  }

  /**
   * Multipart import — bypasses the JSON ApiService.post since we need
   * FormData. Still unwraps the {success,data} envelope.
   */
  importCsv(file: File, columnMap: ColumnMap): Observable<BulkJobDto> {
    const fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('column_map', JSON.stringify(columnMap));
    return this.http
      .post<ApiResponse<BulkJobDto>>('/v1/links/import', fd)
      .pipe(map((r) => unwrapApi(r)));
  }

  exportCsv(filter: ExportCsvRequest): Observable<BulkJobDto> {
    return this.api.post<BulkJobDto, ExportCsvRequest>('/v1/links/export', filter);
  }

  bulkPatch(req: BulkPatchRequest): Observable<BulkJobDto> {
    return this.api.post<BulkJobDto, BulkPatchRequest>('/v1/links/bulk-patch', req);
  }
}

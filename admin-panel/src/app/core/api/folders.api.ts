import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  CreateFolderRequest,
  FolderDto,
  UpdateFolderRequest,
} from '../models/folder.model';

@Injectable({ providedIn: 'root' })
export class FoldersApi {
  private readonly api = inject(ApiService);

  list(): Observable<FolderDto[]> {
    return this.api.get<FolderDto[]>('/v1/folders');
  }

  get(id: string): Observable<FolderDto> {
    return this.api.get<FolderDto>(`/v1/folders/${id}`);
  }

  create(req: CreateFolderRequest): Observable<FolderDto> {
    return this.api.post<FolderDto, CreateFolderRequest>('/v1/folders', req);
  }

  update(id: string, req: UpdateFolderRequest): Observable<FolderDto> {
    return this.api.patch<FolderDto, UpdateFolderRequest>(`/v1/folders/${id}`, req);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/v1/folders/${id}`);
  }

  /** Bulk-move a set of link IDs into a folder (or null to unassign). */
  moveLinks(folderId: string | null, linkIds: string[]): Observable<{ moved: number }> {
    return this.api.post<{ moved: number }>('/v1/folders/move-links', {
      folder_id: folderId,
      link_ids: linkIds,
    });
  }
}

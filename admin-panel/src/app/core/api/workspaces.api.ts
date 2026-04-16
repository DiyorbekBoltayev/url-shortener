import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import {
  SwitchWorkspaceResponse,
  WorkspaceDto,
} from '../models/workspace.model';

@Injectable({ providedIn: 'root' })
export class WorkspacesApi {
  private readonly api = inject(ApiService);

  myWorkspaces(): Observable<WorkspaceDto[]> {
    return this.api.get<WorkspaceDto[]>('/v1/workspaces/me');
  }

  switch(workspaceId: string): Observable<SwitchWorkspaceResponse> {
    return this.api.post<SwitchWorkspaceResponse>('/v1/auth/switch-workspace', {
      workspace_id: workspaceId,
    });
  }
}

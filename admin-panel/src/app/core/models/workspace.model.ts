export type WorkspacePlan = 'free' | 'pro' | 'business' | 'enterprise';
export type WorkspaceRole = 'owner' | 'admin' | 'member' | 'viewer';

export interface WorkspaceDto {
  id: string;
  name: string;
  slug: string;
  plan: WorkspacePlan;
  role: WorkspaceRole;
}

export interface SwitchWorkspaceResponse {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  workspace?: WorkspaceDto;
}

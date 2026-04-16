export interface FolderDto {
  id: string;
  workspace_id: string;
  parent_id: string | null;
  name: string;
  color: string | null;
  children_count: number;
  links_count: number;
  created_at: string;
}

export interface CreateFolderRequest {
  name: string;
  parent_id?: string | null;
  color?: string | null;
}

export interface UpdateFolderRequest {
  name?: string;
  parent_id?: string | null;
  color?: string | null;
}

/** Client-side tree node built from flat folder list. */
export interface FolderTreeNode extends FolderDto {
  children: FolderTreeNode[];
}

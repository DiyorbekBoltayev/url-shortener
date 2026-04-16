export type BulkJobKind = 'import' | 'export' | 'bulk_patch';
export type BulkJobStatus = 'pending' | 'running' | 'done' | 'failed';

export interface BulkJobDto {
  id: string;
  kind: BulkJobKind;
  status: BulkJobStatus;
  total: number;
  done: number;
  failed: number;
  result_url: string | null;
  created_at: string;
  finished_at: string | null;
  error_message?: string | null;
}

export interface BulkPatchRequest {
  ids: string[];
  patch: {
    folder_id?: string | null;
    tags_add?: string[];
    is_active?: boolean;
    delete?: boolean;
  };
}

export interface ExportCsvRequest {
  folder_id?: string | null;
  q?: string;
  tags?: string[];
  domain_id?: string | null;
}

export type ColumnMap = Record<string, string>; // backend field -> csv column header

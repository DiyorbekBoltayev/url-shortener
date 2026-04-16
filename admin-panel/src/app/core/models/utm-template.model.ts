export interface UtmTemplateDto {
  id: string;
  workspace_id: string;
  name: string;
  source: string | null;
  medium: string | null;
  campaign: string | null;
  term: string | null;
  content: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateUtmTemplateRequest {
  name: string;
  source?: string | null;
  medium?: string | null;
  campaign?: string | null;
  term?: string | null;
  content?: string | null;
}

export type UpdateUtmTemplateRequest = Partial<CreateUtmTemplateRequest>;

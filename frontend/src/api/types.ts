// Shapes returned by the backend API (mirror app/schemas.py).

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  role: "admin" | "analyst" | "readonly";
}

export interface Organization {
  id: string;
  name: string;
  aliases: string[];
  primary_domain: string | null;
  additional_domains: string[];
  notes: string | null;
  archived: boolean;
  created_at: string;
}

export interface SourceRef {
  source: string;
  collected_at: string;
  confidence: number;
  evidence_ref: string | null;
}

export interface Asset {
  asset_type: string;
  value: string;
  confidence: number;
  sources: SourceRef[];
  first_seen: string;
  last_seen: string;
  attributes: Record<string, unknown>;
}

export type InvestigationStatus = "draft" | "running" | "complete" | "partial" | "failed" | "success";

export interface Investigation {
  id: string;
  organization_id: string;
  assessment_type: string;
  scope: Record<string, unknown>;
  status: InvestigationStatus;
  authorized_by: string | null;
  authorization_scope: string | null;
  authorized_at: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  assets?: Asset[];
}

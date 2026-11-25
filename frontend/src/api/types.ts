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

export type FindingSeverity = "info" | "low" | "medium" | "high" | "critical";
export type FindingClassification = "confirmed" | "unverified";
export type FindingStatus = "open" | "triaged" | "dismissed";

export interface FindingEvidence {
  asset_type: string;
  value: string;
  confidence: number;
  sources: string[];
}

export interface Finding {
  id: string;
  finding_key: string;
  finding_type: string;
  title: string;
  description: string;
  severity: FindingSeverity;
  confidence: number;
  classification: FindingClassification;
  status: FindingStatus;
  evidence: FindingEvidence[];
  created_at: string;
  updated_at: string;
}

export interface SecretInfo {
  name: string;
  source: "tenant" | "env" | "unset" | string;
  configured: boolean;
  updated_at: string | null;
}

export interface AuditEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  target: string | null;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface PlanStep {
  collector: string;
  description: string;
  passive: boolean;
  required_keys: string[];
  enabled: boolean;
  skip_reason: string | null;
}

export interface DiscoveryPlan {
  target: string | null;
  additional_targets: string[];
  passive_only: boolean;
  enabled_count: number;
  skipped_count: number;
  steps: PlanStep[];
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
  monitoring_enabled: boolean;
  monitoring_interval: string | null;
  assets?: Asset[];
  findings?: Finding[];
  exposure_score?: ExposureScore;
}

export type MonitoringInterval = "hourly" | "daily" | "weekly";

export interface AlertsResponse {
  unacknowledged: number;
  alerts: ChangeEvent[];
}

export type ChangeType =
  | "asset_added"
  | "asset_removed"
  | "finding_appeared"
  | "finding_resolved"
  | "finding_severity_changed";

export interface ChangeEvent {
  id: string;
  change_type: ChangeType;
  entity_type: "asset" | "finding";
  entity_key: string;
  title: string;
  severity: FindingSeverity | null;
  detail: Record<string, unknown>;
  run_at: string;
  acknowledged_at: string | null;
  created_at: string;
}

export interface ExposureScore {
  score: number;
  grade: string;
  label: string;
  counts: Record<string, number>;
  scored_findings: number;
  rationale: string;
}

// --- portfolio dashboard (Phase 5) ---

export interface ExposureLeader {
  investigation_id: string;
  organization_id: string;
  score: number;
  grade: string;
  label: string;
}

export interface PortfolioSummary {
  organizations: { total: number; archived: number };
  investigations_total: number;
  investigations_by_status: Record<string, number>;
  assessed_investigations: number;
  exposure_distribution: Record<string, number>;
  highest_exposure: ExposureLeader | null;
  open_alerts: number;
  monitoring_enabled: number;
  monitoring_by_interval: Record<string, number>;
}

export interface ActivityItem extends ChangeEvent {
  investigation_id: string;
  organization_id: string;
  organization_name: string;
  is_material: boolean;
}

export type MonitorState = "overdue" | "due" | "pending" | "fresh";

export interface MonitoringHealthItem {
  investigation_id: string;
  organization_id: string;
  organization_name: string;
  interval: string | null;
  status: string;
  last_run: string | null;
  next_due_at: string | null;
  state: MonitorState;
}

export interface ExposureHistoryPoint {
  score: number;
  grade: string;
  label: string;
  scored_findings: number;
  run_at: string;
}

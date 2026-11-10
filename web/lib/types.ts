export type Severity = "low" | "medium" | "high";
export type Decision = "open" | "accepted" | "edited" | "ignored";
export type ScanStatus = "draft" | "in_review" | "approved" | "sent_back";
export type RuleKind = "banned_word" | "term" | "tone" | "claim_policy" | "accessibility";

export interface Issue {
  id: string;
  scan_id: string;
  type: string;
  severity: Severity;
  span_start: number;
  span_end: number;
  excerpt: string;
  why: string;
  source_code: string;
  fix: string | null;
  confidence: number;
  needs_human: boolean;
  engine: string;
  decision: Decision;
  decision_reason: string | null;
}

export interface Scan {
  id: string;
  brand_id: string;
  author: string;
  channel: string;
  content: string;
  status: ScanStatus;
  ai_status: "off" | "ok" | "partial" | "error";
  has_image: boolean;
  created_at: string;
  updated_at: string;
}

export interface Version {
  id: string;
  number: number;
  content: string;
  created_by: string;
  note: string;
  created_at: string;
}

export interface Review {
  id: string;
  reviewer: string;
  action: "approve" | "send_back";
  comment: string;
  created_at: string;
}

export interface ScanBundle {
  scan: Scan;
  issues: Issue[];
  versions: Version[];
  reviews: Review[];
}

export interface ScanSummary {
  id: string;
  brand_id: string;
  author: string;
  channel: string;
  status: ScanStatus;
  created_at: string;
  updated_at: string;
  preview: string;
  has_image: boolean;
  open_issues: number;
  total_issues: number;
}

export interface Fact {
  id: string;
  code: string;
  statement: string;
  source: string;
  updated_at: string;
  indexed: boolean;
}

export interface Rule {
  id: string;
  code: string;
  kind: RuleKind;
  pattern: string;
  replacement: string | null;
  message: string;
  severity: Severity;
}

export interface BrandSummary {
  id: string;
  name: string;
}

export interface Brand extends BrandSummary {
  voice_guide: string;
  colors: string[];
  facts: Fact[];
  rules: Rule[];
}

export interface RuleStat {
  source_code: string;
  type: string;
  total: number;
  ignored: number;
  fixed: number;
  sample_reasons: string[] | null;
  override_rate: number;
  unclear: boolean;
}

export interface Insights {
  scans_by_status: Partial<Record<ScanStatus, number>>;
  rules: RuleStat[];
  gap_radar: RuleStat[];
}

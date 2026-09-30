// Hand-written mirror of the API responses. `npm run gen:api` also generates schema.d.ts from /openapi.json.
export type Role = "customer" | "analyst";
export interface User { id: string; email: string; name: string; role: Role }

export type CaseStatus = "draft" | "under_review" | "info_requested" | "approved" | "rejected";
export type Severity = "critical" | "high" | "medium" | "low";

export interface ProgressStep { key: string; label: string; status: "done" | "current" | "todo" }
export interface ExtractedField { key: string; label: string; value: string; confidence: number | null; source: string | null }
export interface DocSummary { id: string; doc_type: string; label: string; fields: ExtractedField[]; missing: string[] }

export type Card =
  | { type: "upload_request"; doc_type: string; label: string; why: string; tips: string[]; remaining: string[] }
  | { type: "confirm"; field: string; label: string; reason: "conflict" | "low_confidence"; options: { value: string; source: string; confidence: number }[] }
  | { type: "field"; field: string; label: string; kind: "text" | "choice" | "bool"; choices: string[]; optional: boolean }
  | { type: "extraction"; doc_type: string; label: string; fields: ExtractedField[]; missing: string[] }
  | { type: "ready"; items: { label: string; value: string }[] }
  | { type: "citations"; items: { title: string; section: string }[] }
  | { type: "submitted"; submission_no: number }
  | { type: "upload_ack"; doc_type: string };

export interface TraceItem { node: string; detail: string }
export interface ChatMessage { id: string; role: "user" | "assistant" | "system"; text: string; ui: Card | null; trace?: TraceItem[] | null; created_at: string }

export interface CaseView {
  id: string; status: CaseStatus; product: string; product_name: string; submission_no: number;
  progress: ProgressStep[]; next_step: { kind: string; field?: string; doc_type?: string };
  documents: DocSummary[]; messages: ChatMessage[];
}

export interface Flag { code: string; severity: Severity; title: string; message: string; confirmed_by_customer: boolean }
export interface Analysis {
  score: number; band: "clean" | "review" | "attention"; flags: Flag[];
  breakdown: { code: string; title: string; penalty: number; reduced_because_confirmed: boolean }[];
  summary: string; provenance: { rules?: { version: number; sha256: string }; summariser?: string; prompts?: Record<string, string> };
}
export interface QueueRow {
  id: string; customer: string; product: string; submitted_at: string; submission_no: number; analysis_ready: boolean;
  score: number | null; band: Analysis["band"] | null; flag_count: number; top_severity: Severity | null;
}
export interface ReviewDetail {
  id: string; status: CaseStatus; customer: { name: string; email: string }; submission_no: number; submitted_at: string | null;
  details: { label: string; value: string; confirmed_by_customer?: boolean }[];
  documents: { id: string; doc_type: string; label: string; fields: ExtractedField[]; quality: { sharpness?: number; pdf_kind?: "text" | "scanned"; pdf_pages?: number }; sha256: string; pages: number }[];
  analysis: Analysis | null; score_bands: { ready: number; review: number };
  decisions: { action: string; note: string; at: string }[];
  conversation: { role: string; text: string }[];
  audit: { id: number; ts: string; actor: string; action: string; details: Record<string, unknown> }[];
  can_decide: boolean;
}
export interface DemoScenario { key: string; title: string; description: string; documents: string[] }

export type StreamEvent =
  | { event: "node"; data: TraceItem }
  | { event: "state"; data: CaseView }
  | { event: "error"; data: { message: string } };

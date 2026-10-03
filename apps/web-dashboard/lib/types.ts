/**
 * types.ts – Canonical TypeScript types.
 * Status and Priority enums MATCH the backend exactly (case-sensitive).
 */

// ── Canonical enums matching backend ─────────────────────────────────────────
export type TicketStatus =
  | "Open"
  | "In Progress"
  | "In Review"
  | "Done"
  | "Closed"
  | "Blocked";

export type TicketPriority = "Low" | "Medium" | "High" | "Critical";

export type TicketType =
  | "bug"
  | "feature"
  | "task"
  | "incident"
  | "code_review"
  | "epic"
  | "story"
  | "spike";

// ── Core ticket model (matches TicketResponse from ticket-service) ────────────
export interface Ticket {
  id:               number;
  ticket_id:        string;   // e.g. "APM-42"
  title:            string;
  description:      string | null;
  ticket_type:      TicketType;
  status:           TicketStatus;
  priority:         TicketPriority;
  priority_score:   number | null;
  assignee:         string | null;
  reported_by:      string | null;
  source:           string | null;
  channel:          string | null;
  slack_message_ts: string | null;
  parent_id:        string | null;   // e.g. "APM-4" when this is a sub-task
  duplicate_of:     string | null;
  created_at:       string;
  updated_at:       string;
}

export interface TicketCreatePayload {
  title:       string;
  description?: string;
  ticket_type?: TicketType;
  priority?:    TicketPriority;
  assignee?:    string;
  source?:      string;
}

export interface TicketUpdatePayload {
  title?:          string;
  description?:    string;
  ticket_type?:    TicketType;
  status?:         TicketStatus;
  priority?:       TicketPriority;
  priority_score?: number;
  assignee?:       string;
  parent_id?:      string;   // "" clears
  duplicate_of?:   string;   // "" clears
  actor?:          string;
  reason?:         string;
}

// ── List response ─────────────────────────────────────────────────────────────
export interface TicketListResponse {
  tickets:   Ticket[];
  total:     number;
  page:      number;
  page_size: number;
}

// ── Stats ─────────────────────────────────────────────────────────────────────
export interface DashboardStats {
  total_tickets:     number;
  active_tickets:    number;
  completed_tickets: number;
  blocked_tickets:   number;
  critical_tickets:  number;
  success_rate:      number;
  by_status:         Record<string, number>;
  by_priority:       Record<string, number>;
}

// ── Filter ────────────────────────────────────────────────────────────────────
export interface TicketFilter {
  status?:      TicketStatus;
  priority?:    TicketPriority;
  ticket_type?: TicketType;
  assignee?:    string;
  search?:      string;
  parent?:      string;
}

// ── API response wrapper ──────────────────────────────────────────────────────
export interface ApiResponse<T> {
  success: boolean;
  data?:   T;
  error?:  string;
  total?:  number;
  page?:   number;
  page_size?: number;
}

// ── Timeline ──────────────────────────────────────────────────────────────────
export type TicketEventKind =
  | "created" | "status_changed" | "priority_changed" | "assigned" | "edited"
  | "linked" | "possible_duplicates" | "subtasks_created" | "agent_session" | "note";

export interface TicketEvent {
  id:         number;
  ticket_id:  string;
  kind:       TicketEventKind;
  actor:      string | null;
  summary:    string;
  data:       Record<string, any> | null;
  created_at: string;
}

// ── Similarity ────────────────────────────────────────────────────────────────
export interface SimilarTicket {
  ticket_id: string;
  title:     string;
  status:    TicketStatus;
  priority:  TicketPriority;
  score:     number;   // 0–1
}

// ── Breakdown ─────────────────────────────────────────────────────────────────
export interface ProposedSubtask {
  title:          string;
  description:    string | null;
  ticket_type:    TicketType;
  estimate_hours: number | null;
  depends_on:     number[];   // 1-based indexes into the proposal
}

export interface BreakdownProposal {
  ticket_id: string;
  summary:   string;
  subtasks:  ProposedSubtask[];
  model:     string;
}

// ── Coding-agent sessions ─────────────────────────────────────────────────────
export type AgentKind = "claude-code" | "codex" | "cursor";

export interface AgentSettings {
  repo_path:      string | null;
  repo_url:       string | null;
  base_branch:    string | null;
  workspaces_dir: string | null;
  default_agent:  AgentKind;
  auto_prepare:   boolean;
  use_worktrees:  boolean;
}

export interface RepoStatus {
  configured:      boolean;
  ok?:             boolean;
  error?:          string;
  path?:           string;
  branch?:         string;
  base_branch?:    string;
  commit?:         string;
  remote?:         string;
  workspaces_dir?: string;
  llm_configured:  boolean;
}

export interface AgentCommand {
  label:      string;
  lines:      string[];
  cli_lines?: string[];
  deeplink?:  string;
}

export interface AgentSession {
  ticket_id:       string;
  agent:           AgentKind;
  mode:            "manual";
  repo_path:       string | null;
  workdir:         string | null;
  branch:          string | null;
  branch_created:  boolean;
  base_branch:     string | null;
  brief_path:      string;
  mcp_config_path: string;
  codex_mcp_toml:  string;
  commands:        Record<AgentKind, AgentCommand>;
  relevant_files:  { path: string; matched: string[] }[];
  test_commands:   string[];
  ai_plan:         boolean;
  notes:           string[];
  created_at:      string;
  updated_at:      string;
}

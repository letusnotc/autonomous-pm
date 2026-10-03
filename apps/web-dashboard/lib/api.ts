/**
 * api.ts – Client-side API utilities.
 * All calls go through Next.js /api/dashboard/* proxy routes.
 */
import type {
  Ticket, TicketCreatePayload, TicketUpdatePayload,
  TicketFilter, DashboardStats, ApiResponse, TicketListResponse,
  TicketEvent, SimilarTicket, BreakdownProposal, ProposedSubtask,
  AgentKind, AgentSession, AgentSettings, RepoStatus,
} from "./types";

const BASE = "/api/dashboard";
const AGENT = "/api/agent";

async function request<T>(
  path: string,
  options: RequestInit = {},
  base: string = BASE,
): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${base}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    const json = await res.json();
    if (!res.ok) return { success: false, error: json.error || res.statusText };
    return json;
  } catch (err: any) {
    return { success: false, error: err?.message || "Network error" };
  }
}

export async function getStats(): Promise<ApiResponse<DashboardStats>> {
  return request<DashboardStats>("/stats");
}

export async function getTickets(
  page = 1,
  pageSize = 20,
  filters: TicketFilter = {}
): Promise<ApiResponse<TicketListResponse>> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters.status)      params.set("status",      filters.status);
  if (filters.priority)    params.set("priority",     filters.priority);
  if (filters.ticket_type) params.set("ticket_type",  filters.ticket_type);
  if (filters.assignee)    params.set("assignee",     filters.assignee);
  if (filters.search)      params.set("search",       filters.search);
  if (filters.parent)      params.set("parent",       filters.parent);
  return request<TicketListResponse>(`/tickets?${params}`);
}

export async function getTicket(id: string): Promise<ApiResponse<Ticket>> {
  return request<Ticket>(`/tickets/${id}`);
}

export async function createTicket(
  payload: TicketCreatePayload
): Promise<ApiResponse<Ticket>> {
  return request<Ticket>("/tickets", {
    method: "POST",
    body: JSON.stringify({ source: "dashboard", actor: "dashboard", ...payload }),
  });
}

export async function updateTicket(
  id: string,
  payload: TicketUpdatePayload
): Promise<ApiResponse<Ticket>> {
  return request<Ticket>(`/tickets/${id}`, {
    method: "PUT",
    body: JSON.stringify({ actor: "dashboard", ...payload }),
  });
}

export async function deleteTicket(id: string): Promise<ApiResponse<{ deleted: boolean }>> {
  return request<{ deleted: boolean }>(`/tickets/${id}`, { method: "DELETE" });
}

export async function assignTicket(
  id: string,
  assignee: string
): Promise<ApiResponse<Ticket>> {
  return request<Ticket>(`/tickets/${id}/assign`, {
    method: "POST",
    body: JSON.stringify({ assignee }),
  });
}

// ── Timeline, duplicates, sub-tasks ───────────────────────────────────────────

export async function getEvents(id: string): Promise<ApiResponse<TicketEvent[]>> {
  return request<TicketEvent[]>(`/tickets/${id}/events`);
}

export async function getSimilar(id: string, minScore = 0.35): Promise<ApiResponse<SimilarTicket[]>> {
  return request<SimilarTicket[]>(`/tickets/${id}/similar?limit=3&min_score=${minScore}`);
}

export async function findSimilar(title: string, description?: string): Promise<ApiResponse<SimilarTicket[]>> {
  return request<SimilarTicket[]>("/tickets/similar", {
    method: "POST",
    body: JSON.stringify({ title, description, limit: 3, min_score: 0.3 }),
  });
}

export async function getSubtasks(id: string): Promise<ApiResponse<TicketListResponse>> {
  return getTickets(1, 100, { parent: id });
}

export async function addSubtasks(
  id: string,
  subtasks: { title: string; ticket_type?: string; description?: string }[],
): Promise<ApiResponse<Ticket[]>> {
  return request<Ticket[]>(`/tickets/${id}/subtasks`, {
    method: "POST",
    body: JSON.stringify({ subtasks, actor: "dashboard" }),
  });
}

// ── Dev Agent Service: breakdown + coding-agent sessions ──────────────────────

export async function proposeBreakdown(id: string): Promise<ApiResponse<BreakdownProposal>> {
  return request<BreakdownProposal>(`/tickets/${id}/breakdown`, { method: "POST" }, AGENT);
}

export async function applyBreakdown(id: string, subtasks: ProposedSubtask[]): Promise<ApiResponse<Ticket[]>> {
  return request<Ticket[]>(`/tickets/${id}/breakdown/apply`, {
    method: "POST",
    body: JSON.stringify({ subtasks }),
  }, AGENT);
}

export async function getSession(id: string): Promise<ApiResponse<AgentSession>> {
  return request<AgentSession>(`/tickets/${id}/session`, {}, AGENT);
}

export async function prepareSession(
  id: string, agent: AgentKind, includeAiPlan: boolean,
): Promise<ApiResponse<AgentSession>> {
  return request<AgentSession>(`/tickets/${id}/session`, {
    method: "POST",
    body: JSON.stringify({ agent, include_ai_plan: includeAiPlan }),
  }, AGENT);
}

export async function getBrief(id: string): Promise<ApiResponse<string>> {
  return request<string>(`/tickets/${id}/brief`, {}, AGENT);
}

export async function getAgentSettings(): Promise<ApiResponse<AgentSettings>> {
  return request<AgentSettings>("/settings", {}, AGENT);
}

export async function saveAgentSettings(settings: AgentSettings): Promise<ApiResponse<AgentSettings>> {
  return request<AgentSettings>("/settings", { method: "PUT", body: JSON.stringify(settings) }, AGENT);
}

export async function getRepoStatus(): Promise<ApiResponse<RepoStatus>> {
  return request<RepoStatus>("/repo/status", {}, AGENT);
}

/**
 * /api/dashboard/tickets/[id]/events → GET /tickets/{id}/events (timeline)
 */
import { NextRequest } from "next/server";
import { proxy, TICKET_SERVICE_URL } from "@/lib/proxy";

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  return proxy(`${TICKET_SERVICE_URL}/tickets/${encodeURIComponent(params.id)}/events`, {}, "Failed to load timeline");
}

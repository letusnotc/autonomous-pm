/**
 * /api/dashboard/tickets/[id]/similar → GET /tickets/{id}/similar
 */
import { NextRequest } from "next/server";
import { proxy, TICKET_SERVICE_URL } from "@/lib/proxy";

export async function GET(request: NextRequest, { params }: { params: { id: string } }) {
  const query = new URL(request.url).searchParams.toString();
  return proxy(`${TICKET_SERVICE_URL}/tickets/${encodeURIComponent(params.id)}/similar?${query}`, {},
    "Failed to load similar tickets");
}

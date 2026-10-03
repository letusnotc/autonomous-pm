/**
 * /api/dashboard/tickets/[id]/subtasks → POST /tickets/{id}/subtasks
 */
import { NextRequest } from "next/server";
import { proxy, TICKET_SERVICE_URL } from "@/lib/proxy";

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  const body = await request.text();
  return proxy(`${TICKET_SERVICE_URL}/tickets/${encodeURIComponent(params.id)}/subtasks`,
    { method: "POST", body }, "Failed to create sub-tasks");
}

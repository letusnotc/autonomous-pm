/**
 * /api/dashboard/tickets/similar → POST /tickets/similar (duplicate check for a draft)
 */
import { NextRequest } from "next/server";
import { proxy, TICKET_SERVICE_URL } from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxy(`${TICKET_SERVICE_URL}/tickets/similar`, { method: "POST", body }, "Similarity check failed");
}

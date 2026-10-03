/**
 * /api/agent/* → Dev Agent Service (settings, breakdown, coding-agent sessions)
 */
import { NextRequest } from "next/server";
import { proxy, DEV_AGENT_SERVICE_URL } from "@/lib/proxy";

// Only these service paths are reachable through the dashboard.
const ALLOWED = [
  /^settings$/,
  /^repo\/status$/,
  /^tickets\/APM-\d+\/(breakdown|breakdown\/apply|session|brief)$/i,
];

async function forward(request: NextRequest, path: string[], method: string) {
  const joined = path.map(encodeURIComponent).join("/");
  if (!ALLOWED.some(rx => rx.test(path.join("/")))) {
    return Response.json({ success: false, error: "Not found" }, { status: 404 });
  }
  const body = method === "GET" ? undefined : await request.text();
  return proxy(`${DEV_AGENT_SERVICE_URL}/${joined}`, { method, body: body || undefined }, "Dev Agent Service error");
}

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return forward(req, params.path, "GET");
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return forward(req, params.path, "POST");
}
export async function PUT(req: NextRequest, { params }: { params: { path: string[] } }) {
  return forward(req, params.path, "PUT");
}

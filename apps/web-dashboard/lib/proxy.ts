/**
 * proxy.ts – Server-side helper for API routes: forwards a request to a
 * backend service and wraps the reply in the dashboard's { success, data } envelope.
 */
import { NextResponse } from "next/server";

export const TICKET_SERVICE_URL    = process.env.TICKET_SERVICE_URL    || "http://localhost:3001";
export const DEV_AGENT_SERVICE_URL = process.env.DEV_AGENT_SERVICE_URL || "http://localhost:3007";

export async function proxy(url: string, init: RequestInit = {}, fallbackError = "Request failed") {
  try {
    const res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      cache: "no-store",
    });
    const type = res.headers.get("content-type") || "";
    const body = type.includes("application/json") ? await res.json().catch(() => null) : await res.text();
    if (!res.ok) {
      const detail = typeof body === "object" && body ? body.detail : null;
      const error = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : fallbackError;
      return NextResponse.json({ success: false, error }, { status: res.status });
    }
    return NextResponse.json({ success: true, data: body });
  } catch (err: any) {
    const offline = err?.cause?.code === "ECONNREFUSED";
    return NextResponse.json(
      { success: false, error: offline ? `Service unavailable (${new URL(url).host})` : err?.message || fallbackError },
      { status: 502 },
    );
  }
}

/**
 * /health – liveness check used by scripts/health-check.sh and container orchestrators.
 */
export function GET() {
  return Response.json({ status: "ok", service: "web-dashboard" });
}

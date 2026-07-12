// FastAPI error bodies come in two shapes: HTTPException gives
// `{detail: "..."}` (a string); Pydantic request-validation errors give
// `{detail: [{msg, loc, type}, ...]}` (an array) — e.g. the webhook SSRF
// guard's 422. Handle both so the actionable message reaches the user.
export function extractApiErrorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d as { msg?: unknown } | null)?.msg)
      .filter((m): m is string => typeof m === "string")
    if (msgs.length > 0) return msgs.join("; ")
  }
  return fallback
}

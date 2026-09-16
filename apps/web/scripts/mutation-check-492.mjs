// Mutation check for the #492 error-boundary + relay tests (issue #493).
// Run from apps/web in a CLEAN worktree — it rewrites source files in place and
// restores them, so nothing else may be editing the tree. Exit 1 if any survive.
// For each mutation: apply the exact text substitution, run only the matching
// jest file, record KILLED (jest failed) or SURVIVED (jest passed), restore.
import { readFileSync, writeFileSync } from "node:fs"
import { spawnSync } from "node:child_process"

const ROUTE = "src/app/api/monitoring/route.ts"
const ROUTE_T = "__tests__/app/api/monitoring/route.test.ts"
const RCE = "src/lib/report-client-error.ts"
const RCE_T = "__tests__/lib/report-client-error.test.ts"
const GE = "src/app/global-error.tsx"
const GE_T = "__tests__/app/global-error.test.tsx"
const ERR = "src/app/error.tsx"
const ERR_T = "__tests__/app/error.test.tsx"

const M = [
  { id: "route: remove `if (!dsn) return 204` gate", file: ROUTE, test: ROUTE_T, edits: [[
    '  const dsn = process.env.SENTRY_DSN\n  if (!dsn) return new Response(null, { status: 204 })\n',
    '  const dsn = process.env.SENTRY_DSN as string\n']] },
  { id: "route: envelope header event_id differs from event's", file: ROUTE, test: ROUTE_T, edits: [[
    'JSON.stringify({ event_id: eventId, sent_at: sentAt })',
    'JSON.stringify({ event_id: crypto.randomUUID().replace(/-/g, ""), sent_at: sentAt })']] },
  { id: "route: drop the `exception` field", file: ROUTE, test: ROUTE_T, edits: [[
    '    exception: { values: [{ type: "Error", value: message }] },\n', '']] },
  { id: "route: remove the truncation `.slice()` in str()", file: ROUTE, test: ROUTE_T, edits: [[
    '  return value.slice(0, max)', '  return value']] },
  { id: "route: str() coerces with String() instead of dropping", file: ROUTE, test: ROUTE_T, edits: [[
    '  if (typeof value !== "string" || value.length === 0) return undefined\n  return value.slice(0, max)',
    '  if (value === undefined || value === null || value === "") return undefined\n  return String(value).slice(0, max)']] },
  { id: "route: remove the Content-Length pre-check", file: ROUTE, test: ROUTE_T, edits: [[
    '  const declared = Number(request.headers.get("content-length"))\n  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {\n    return new Response(null, { status: 413 })\n  }\n', '']] },
  { id: "route: remove the Sec-Fetch-Site gate", file: ROUTE, test: ROUTE_T, edits: [[
    '  const fetchSite = request.headers.get("sec-fetch-site")\n  if (fetchSite && fetchSite !== "same-origin") {\n    return new Response(null, { status: 403 })\n  }\n', '']] },
  { id: "route: drop the `fingerprint`", file: ROUTE, test: ROUTE_T, edits: [[
    '    ...(digest ? { fingerprint: ["{{ default }}", digest] } : {}),\n', '']] },
  { id: "route: remove the `!ingest.ok` check", file: ROUTE, test: ROUTE_T, edits: [[
    '    if (!ingest.ok) {', '    if (!ingest) {']] },

  { id: "report-client-error: keepalive true → false", file: RCE, test: RCE_T, edits: [[
    '      keepalive: true,', '      keepalive: false,']] },
  { id: "report-client-error: send location.href instead of pathname", file: RCE, test: RCE_T, edits: [[
    '        pathname: window.location.pathname,', '        pathname: window.location.href,']] },
  { id: "report-client-error: remove the try/catch", file: RCE, test: RCE_T, edits: [
    ['  try {\n    void fetch(', '  {\n    void fetch('],
    ['  } catch {\n    // no fetch, or a runtime that refuses it — nothing to do but carry on\n  }', '  }']] },
  { id: "report-client-error: remove the truncation", file: RCE, test: RCE_T, edits: [[
    '        message: error.message?.slice(0, MAX_MESSAGE),\n        stack: error.stack?.slice(0, MAX_STACK),',
    '        message: error.message,\n        stack: error.stack,']] },
  { id: "report-client-error: change the URL", file: RCE, test: RCE_T, edits: [[
    '    void fetch("/api/monitoring", {', '    void fetch("/api/monitor", {']] },

  { id: "global-error: return the fallback without <html>/<body>", file: GE, test: GE_T, edits: [[
    '    <html lang="en">\n      <body>\n        <ErrorFallback error={error} reset={reset} />\n      </body>\n    </html>',
    '    <ErrorFallback error={error} reset={reset} />']] },
  { id: "global-error: remove the reportClientError call", file: GE, test: GE_T, edits: [[
    '    reportClientError(error, "global-error")\n', '']] },
  { id: "error: remove the reportClientError call", file: ERR, test: ERR_T, edits: [[
    '    reportClientError(error, "route-error")\n', '']] },
]

const only = process.argv[2] // optional substring filter
const rows = []
for (const m of M) {
  if (only && !m.id.includes(only)) continue
  const original = readFileSync(m.file, "utf8")
  let mutated = original
  for (const [from, to] of m.edits) {
    const n = mutated.split(from).length - 1
    if (n !== 1) throw new Error(`${m.id}: expected exactly 1 match, found ${n} for:\n${from}`)
    mutated = mutated.replace(from, to)
  }
  writeFileSync(m.file, mutated)
  let out
  try {
    const r = spawnSync("npx", ["jest", m.test], { encoding: "utf8", env: { ...process.env, CI: "1" } })
    out = { status: r.status, text: r.stdout + r.stderr }
  } finally {
    writeFileSync(m.file, original)
  }
  if (readFileSync(m.file, "utf8") !== original) throw new Error(`${m.id}: restore failed`)
  const failing = [...new Set([...out.text.matchAll(/^  ● .+? › (.+)$/gm)].map((x) => x[1]))]
  const summary = (out.text.match(/^Tests:.*$/m) ?? ["?"])[0]
  const verdict = out.status === 0 ? "SURVIVED" : "KILLED"
  rows.push({ id: m.id, verdict, failing, summary })
  console.error(`${verdict.padEnd(8)} ${m.id}  [${summary}]`)
}
console.log("| # | Mutation | Result | Failing test(s) |")
console.log("|---|---|---|---|")
rows.forEach((r, i) =>
  console.log(`| ${i + 1} | ${r.id} | ${r.verdict} | ${r.failing.map((f) => `\`${f}\``).join("<br>") || "—"} |`))
const survived = rows.filter((r) => r.verdict === "SURVIVED").length
console.error(`\n${rows.length - survived}/${rows.length} killed, ${survived} survived`)
process.exit(survived ? 1 : 0)

// jev-search: a portal skill for Peruvian job boards that a plain fetch cannot read
// (stateful JSF apps like Talento Perú, SPAs, search forms), driven by jev-browse.
//
// jev-browse (https://github.com/0x7067/jev-browse, MIT) is vendored as a git submodule
// at vendor/jev-browse and run through its committed bundle (bundled/cli.mjs), so this
// skill has zero runtime dependencies of its own and picks up jev-browse updates with
// `git submodule update --remote vendor/jev-browse`. jev-browse drives a real Chrome:
// TypeSafe's Jev model picks one operation and one element per step from an indexed
// table of the page, and a small text model writes typed text and the final answer.
//
// Every run is gated before Chrome starts: the start URL must pass the repo's robots.txt
// check (tools/robots_check.py, the same gate 09-web-research.md uses), the model
// credentials must be configured, and jev-browse always runs with --stop-at-challenge, so
// a CAPTCHA or verification page ends the run instead of being worked around.

import { existsSync, readFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { createHash } from "node:crypto"

export const REPO_ROOT = resolve(import.meta.dir, "../../../../..")

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

// ---------------------------------------------------------------------------
// Sites
// ---------------------------------------------------------------------------

export interface Site {
  id: string
  name: string
  /** Start URL; `{q}` / `{l}` are replaced by the URL-encoded query / location. */
  url: string | null
  /** How to reach the result list from the start URL, in plain words for the agent. */
  howToSearch: string
  notes: string
}

export const SITES: Site[] = [
  {
    id: "talentoperu",
    name: "Talento Perú (SERVIR) - empleo y prácticas en el Estado",
    url: "https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/ofertas_laborales.xhtml",
    howToSearch:
      'Type the search terms into the "Puesto" field (leave it empty when no terms are given), choose the ' +
      "departamento in the location dropdown when a location is given, then press the search button " +
      '("Buscar"). Each result card shows the job title, the public entity, "Ubicación", "Número de ' +
      'Convocatoria", "Cantidad de Vacantes", "Remuneración" and the publication start and end dates.',
    notes:
      "JSF/PrimeFaces app with no stable per-posting URL: postings are identified by their convocatoria " +
      "number. Read the closing date (Fecha Fin de Publicación) as the deadline.",
  },
  {
    id: "laborum",
    name: "Laborum Perú",
    url: "https://www.laborum.pe/",
    howToSearch:
      "Use the site's job search box: type the search terms, add the location when one is given, and submit.",
    notes: "Client-rendered site on a different platform from Bumeran; no public API found.",
  },
  {
    id: "practicas",
    name: "Prácticas.pe - convocatorias de prácticas",
    url: "https://www.practicas.pe/?s={q}",
    howToSearch: "The start URL is already the site's search for the terms; read the listed posts.",
    notes: "WordPress aggregator of internship calls, mostly from the public sector. Each post links to its source.",
  },
  {
    id: "empleosperu",
    name: "Empleos Perú (MTPE)",
    url: "https://www.empleosperu.gob.pe/portal-mtpe/",
    howToSearch:
      "Open the job offers search (ofertas de empleo / bolsa de trabajo), type the search terms, choose the " +
      "location when one is given, and submit.",
    notes: "Ministry of Labour job board (single-page app).",
  },
  {
    id: "indeed",
    name: "Indeed Perú",
    url: "https://pe.indeed.com/jobs?q={q}&l={l}",
    howToSearch: "The start URL is already the search for the terms and location; read the result cards.",
    notes:
      "Usually behind a bot check: with --stop-at-challenge the run ends as verification_required rather " +
      "than attempting it. robots.txt permits /jobs?q= for Claude-User as of 2026-10-15.",
  },
  {
    id: "url",
    name: "Any other board (e.g. your university's bolsa de trabajo) - pass --url",
    url: null,
    howToSearch:
      "Find this site's job search or job list, search for the terms when given, and read the listed postings.",
    notes:
      "Pages behind a login use the jev-browse Chrome profile (~/.jev-browse/profile): sign in there once by " +
      "hand. Page text is sent to the model providers, so only use this on boards whose content you accept sharing.",
  },
]

export function findSite(id: string): Site | undefined {
  return SITES.find((s) => s.id === id)
}

export function buildStartUrl(site: Site, query?: string, location?: string, override?: string): string {
  const template = override ?? site.url
  if (!template) throw new Error(`site "${site.id}" needs --url`)
  return template.replaceAll("{q}", encodeURIComponent(query ?? "")).replaceAll("{l}", encodeURIComponent(location ?? ""))
}

// ---------------------------------------------------------------------------
// Goals. The agent is told exactly what to return, and what it must never do.
// ---------------------------------------------------------------------------

const GUARDRAILS =
  "Only read. Never click apply, postular, inscribirse or similar buttons, never sign in or create an " +
  "account, never type personal data, and never submit any form other than the site's own job search. If " +
  "a CAPTCHA, verification page or login wall appears, stop."

const RESULT_SHAPE =
  "a JSON array (no prose, no code fences) with one object per posting, using exactly these keys: " +
  '"title", "company" (employer or public entity), "location", "modality" ("presencial", "híbrido", ' +
  '"remoto", or null when the posting does not say), "salary" (as written, or null), "deadline" ' +
  '(application closing date as YYYY-MM-DD, or null), "date" (publication date as YYYY-MM-DD, or null), ' +
  '"url" (the posting\'s own link if one is visible on the page, else null), "ref" (convocatoria number or ' +
  "posting id if shown, else null). Copy values as shown on the page; use null for anything not shown."

export function buildSearchGoal(site: Site, opts: { query?: string; location?: string; limit: number }): string {
  const what = [
    opts.query ? `job postings matching "${opts.query}"` : "the most recent job postings",
    opts.location ? `in "${opts.location}" (Peru)` : "in Peru",
  ].join(" ")
  return [
    `Find ${what} on this site. ${site.howToSearch}`,
    `When the result list is visible, answer with ${RESULT_SHAPE} Include at most ${opts.limit} postings, in the order the site lists them.`,
    GUARDRAILS,
  ].join(" ")
}

export function buildDetailGoal(): string {
  return [
    "Read the job posting on this page (open its full description if it is collapsed).",
    "Answer with a single JSON object (no prose, no code fences) with exactly these keys:",
    '"title", "company", "location", "modality" ("presencial", "híbrido", "remoto", or null when not stated),',
    '"salary" (as written, or null), "deadline" (YYYY-MM-DD or null), "date" (YYYY-MM-DD or null),',
    '"contract" (contract type / régimen as written, or null), "schedule" (horario or jornada as written, or null),',
    '"requirements" (array of strings), "description" (the full description text), "how_to_apply" (as written, or null).',
    GUARDRAILS,
  ].join(" ")
}

// ---------------------------------------------------------------------------
// Answer parsing
// ---------------------------------------------------------------------------

export type Modality = "presencial" | "híbrido" | "remoto" | null

export function normalizeModality(value: unknown): Modality {
  if (typeof value !== "string") return null
  const low = value.toLowerCase()
  if (/h[ií]brid|hybrid|presencial y remoto|semipresencial/.test(low)) return "híbrido"
  if (/remot|teletrabajo|home office/.test(low)) return "remoto"
  if (/presencial|on-?site/.test(low)) return "presencial"
  return null
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string | null
  modality: Modality
  salary: string | null
  deadline: string | null
  ref: string | null
  site: string
}

/** First JSON value of the wanted kind in a model answer, tolerating fences and prose. */
export function extractJson(answer: string, kind: "array" | "object"): unknown {
  const text = answer.replace(/```(?:json)?/gi, "")
  const open = kind === "array" ? "[" : "{"
  const close = kind === "array" ? "]" : "}"
  for (let start = text.indexOf(open); start !== -1; start = text.indexOf(open, start + 1)) {
    for (let end = text.lastIndexOf(close); end > start; end = text.lastIndexOf(close, end - 1)) {
      try {
        return JSON.parse(text.slice(start, end + 1))
      } catch {
        // try a shorter span
      }
    }
  }
  throw new Error(`the answer contained no parseable JSON ${kind}`)
}

function str(v: unknown): string | null {
  if (typeof v === "number") return String(v)
  if (typeof v !== "string") return null
  const t = v.trim()
  return t && t.toLowerCase() !== "null" ? t : null
}

function isoDate(v: unknown): string | null {
  const s = str(v)
  if (!s) return null
  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`
  const dmy = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/)
  if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`
  return null
}

function httpUrl(v: unknown, base: string): string | null {
  const s = str(v)
  if (!s) return null
  try {
    const u = new URL(s, base)
    return u.protocol === "http:" || u.protocol === "https:" ? u.toString() : null
  } catch {
    return null
  }
}

export function stableId(site: string, parts: Array<string | null>): string {
  return createHash("sha1").update([site, ...parts].join("|").toLowerCase()).digest("hex").slice(0, 16)
}

export function parseSearchAnswer(answer: string, site: string, startUrl: string): JobCard[] {
  const data = extractJson(answer, "array")
  if (!Array.isArray(data)) throw new Error("the answer is not a JSON array")
  const cards: JobCard[] = []
  for (const raw of data) {
    if (!raw || typeof raw !== "object") continue
    const r = raw as Record<string, unknown>
    const title = str(r.title)
    if (!title) continue
    const company = str(r.company)
    const url = httpUrl(r.url, startUrl)
    const ref = str(r.ref)
    cards.push({
      id: ref ? `${site}:${ref}` : url ?? stableId(site, [title, company, str(r.location)]),
      title,
      company,
      location: str(r.location),
      date: isoDate(r.date),
      url,
      modality: normalizeModality(r.modality),
      salary: str(r.salary),
      deadline: isoDate(r.deadline),
      ref,
      site,
    })
  }
  return cards
}

export interface JobDetail {
  title: string | null
  company: string | null
  location: string | null
  modality: Modality
  salary: string | null
  deadline: string | null
  date: string | null
  contract: string | null
  schedule: string | null
  requirements: string[]
  description: string | null
  howToApply: string | null
  url: string
}

export function parseDetailAnswer(answer: string, url: string): JobDetail {
  const data = extractJson(answer, "object")
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("the answer is not a JSON object")
  const r = data as Record<string, unknown>
  return {
    title: str(r.title),
    company: str(r.company),
    location: str(r.location),
    modality: normalizeModality(r.modality),
    salary: str(r.salary),
    deadline: isoDate(r.deadline),
    date: isoDate(r.date),
    contract: str(r.contract),
    schedule: str(r.schedule),
    requirements: Array.isArray(r.requirements) ? r.requirements.map(str).filter((x): x is string => !!x) : [],
    description: str(r.description),
    howToApply: str(r.how_to_apply),
    url,
  }
}

// ---------------------------------------------------------------------------
// Preconditions: jev-browse installed, Node 22+, credentials, robots.txt
// ---------------------------------------------------------------------------

export function jevCliPath(env: Record<string, string | undefined> = process.env): string {
  return env.JEV_BROWSE_CLI ?? join(REPO_ROOT, "vendor", "jev-browse", "bundled", "cli.mjs")
}

/** Key names set in a dotenv file (values are never read into the result). */
export function dotenvKeys(path: string): Set<string> {
  const keys = new Set<string>()
  if (!existsSync(path)) return keys
  for (const raw of readFileSync(path, "utf8").split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith("#")) continue
    const eq = line.indexOf("=")
    if (eq <= 0) continue
    const value = line.slice(eq + 1).trim().replace(/^["']|["']$/g, "")
    if (value) keys.add(line.slice(0, eq).trim())
  }
  return keys
}

/**
 * The credential variables jev-browse needs that are set nowhere it looks: the
 * environment, then .env in its package root and in the working directory (the
 * repo root, where this CLI runs it).
 */
export function missingCredentials(
  env: Record<string, string | undefined> = process.env,
  envFiles: string[] = [join(REPO_ROOT, "vendor", "jev-browse", ".env"), join(REPO_ROOT, ".env")],
): string[] {
  const fileKeys = new Set(envFiles.flatMap((f) => [...dotenvKeys(f)]))
  const has = (k: string) => !!env[k] || fileKeys.has(k)
  const missing: string[] = []
  if (!has("TYPESAFE_API_KEY") && !has("OPENROUTER_API_KEY")) missing.push("TYPESAFE_API_KEY or OPENROUTER_API_KEY")
  if (!has("TEXT_MODEL_API_KEY")) missing.push("TEXT_MODEL_API_KEY")
  return missing
}

export type Runner = (cmd: string[], opts?: { timeoutMs?: number }) => Promise<{ code: number; stdout: string; stderr: string }>

export const defaultRunner: Runner = async (cmd, opts = {}) => {
  const proc = Bun.spawn(cmd, { cwd: REPO_ROOT, stdout: "pipe", stderr: "pipe" })
  let timer: ReturnType<typeof setTimeout> | undefined
  if (opts.timeoutMs) timer = setTimeout(() => proc.kill(), opts.timeoutMs)
  const [stdout, stderr, code] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ])
  if (timer) clearTimeout(timer)
  return { code, stdout, stderr }
}

export async function nodeMajorVersion(run: Runner = defaultRunner): Promise<number | null> {
  try {
    const { code, stdout } = await run(["node", "--version"])
    const m = stdout.trim().match(/^v(\d+)\./)
    return code === 0 && m ? Number(m[1]) : null
  } catch {
    return null
  }
}

/** tools/robots_check.py: exit 0 = robots.txt permits the URL for Claude-User and *. */
export async function robotsAllows(url: string, run: Runner = defaultRunner): Promise<{ ok: boolean; message: string }> {
  for (const python of ["python", "python3"]) {
    try {
      const { code, stdout, stderr } = await run([python, join(REPO_ROOT, "tools", "robots_check.py"), url], { timeoutMs: 60_000 })
      const message = (stdout || stderr).trim()
      if (code === 0) return { ok: true, message }
      if (code === 1) return { ok: false, message }
    } catch {
      // interpreter not found: try the next name
    }
  }
  return { ok: false, message: "could not run tools/robots_check.py (Python missing); refusing to start without a robots.txt verdict" }
}

export interface RunResult {
  status: "done" | "blocked" | "error"
  final_url?: string
  steps?: number
  elapsed_ms?: number
  answer?: string
  answer_note?: string
  blocked_cause?: string
  challenge_reasons?: string[]
  error?: string
}

export function jevArgs(url: string, goal: string, opts: { maxSteps: number; headed: boolean; cli: string }): string[] {
  const args = ["node", opts.cli, "--url", url, "--goal", goal, "--max-steps", String(opts.maxSteps), "--stop-at-challenge"]
  if (opts.headed) args.push("--headed")
  return args
}

/** Run jev-browse and return its final RunResult (stdout carries only that JSON line). */
export async function runJev(args: string[], timeoutMs: number, run: Runner = defaultRunner): Promise<RunResult> {
  const { stdout, stderr } = await run(args, { timeoutMs })
  const line = stdout.trim().split(/\r?\n/).filter(Boolean).pop()
  if (!line) {
    const tail = stderr.trim().split(/\r?\n/).slice(-3).join(" | ")
    throw new Error(`jev-browse returned no result${tail ? `: ${tail}` : ""}`)
  }
  return JSON.parse(line) as RunResult
}

// ---------------------------------------------------------------------------
// Shared by the search and detail commands
// ---------------------------------------------------------------------------

/** Everything that must hold before Chrome starts. Returns an exit code, or null to proceed. */
export async function preflight(url: string, run: Runner = defaultRunner): Promise<number | null> {
  const cli = jevCliPath()
  if (!existsSync(cli)) {
    writeError(
      `jev-browse is not installed at ${cli}. Run: git submodule update --init vendor/jev-browse`,
      "JEV_NOT_INSTALLED",
    )
    return 1
  }
  const major = await nodeMajorVersion(run)
  if (major === null || major < 22) {
    writeError(`jev-browse needs Node 22 or later on PATH (found ${major ?? "none"})`, "NODE_MISSING")
    return 1
  }
  const missing = missingCredentials()
  if (missing.length) {
    writeError(
      `missing ${missing.join(" and ")}: set them in the environment or in .env at the repo root ` +
        "(gitignored). Every run makes paid model calls; see SKILL.md.",
      "MISSING_CREDENTIALS",
    )
    return 1
  }
  const robots = await robotsAllows(url, run)
  if (!robots.ok) {
    writeError(`robots.txt gate refused ${url}: ${robots.message}`, "ROBOTS_DISALLOWED")
    return 1
  }
  return null
}

/** Map a non-done RunResult to the stderr error contract. */
export function reportUnfinished(result: RunResult): number {
  if (result.blocked_cause === "verification_required" || result.challenge_reasons?.length) {
    writeError(
      `the site showed a CAPTCHA or verification page (${(result.challenge_reasons ?? []).join(", ") || "challenge"}); ` +
        "jev-search never works around these. Use the WebSearch fallback for this board.",
      "VERIFICATION_REQUIRED",
    )
  } else if (result.status === "blocked") {
    writeError(`jev-browse stopped before finishing: ${result.blocked_cause ?? result.answer_note ?? "blocked"}`, "BLOCKED")
  } else {
    writeError(`jev-browse failed: ${result.error ?? result.answer_note ?? "unknown error"}`, "JEV_ERROR")
  }
  return 1
}


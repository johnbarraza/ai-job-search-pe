// Data source: bumeran.com.pe's own JSON API (same origin, no separate api. subdomain).
// Bumeran is a fully client-rendered React SPA with no server-rendered HTML at all (every
// page returns the same empty shell), so this CLI talks to the backend API directly instead
// of parsing markup. The Peru site needs an `x-site-id: BMPE` header and, unlike the
// Argentine site this skill was adapted from, serves the API to an honest tool-naming
// User-Agent with no cookie warm-up (verified live, October 2026). See ../url-reference.md.
//
// Adapted from the Bumeran Argentina skill in the GabrielMensi/ai-job-search fork (same
// Navent/Jobint backend). Peru additions: server-side facet filters (region, district,
// work mode, posting age, seniority) using the `{id, value: <idSemantico>}` filtro shape,
// which the Argentine investigation had not cracked.

import { classifyLevel, normalizeModality, type Level, type Modality } from "./peru.js"

export const BASE_URL = "https://www.bumeran.com.pe"
const SITE_ID = "BMPE"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

// Honest, tool-naming UA per the add-portal contract (never a browser impersonation).
const UA = "Mozilla/5.0 (compatible; bumeran-cli/1.0)"

interface ApiRequestOpts {
  method?: "GET" | "POST"
  body?: unknown
}

/**
 * Call a bumeran.com.pe `/api/...` path with the required `x-site-id` header,
 * exponential backoff on 429/5xx, and null on 404 rather than throwing (a missing job
 * id is an expected outcome for `detail`).
 */
export async function apiRequest<T>(path: string, opts: ApiRequestOpts = {}): Promise<T | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const res = await fetch(`${BASE_URL}/${path.replace(/^\/+/, "")}`, {
      method: opts.method ?? "GET",
      headers: {
        "User-Agent": UA,
        Accept: "application/json, text/plain, */*",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        Origin: BASE_URL,
        Referer: `${BASE_URL}/`,
        "x-site-id": SITE_ID,
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
    })

    if (res.status === 429 || res.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${res.status} ${res.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (res.status === 404) return null
    if (!res.ok) {
      let message = `Request failed: ${res.status} ${res.statusText}`
      try {
        const errBody = (await res.json()) as { message?: string }
        if (errBody?.message) message = errBody.message
      } catch {
        // ignore — fall back to the generic message
      }
      throw new Error(message)
    }
    return (await res.json()) as T
  }
  throw new Error("Request failed after max retries")
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  companyUrl: string | null
  location: string | null
  date: string | null
  url: string
  workMode: string | null
  /** Work mode in the shared Peru vocabulary (src/peru.ts), from modalidadTrabajo. */
  modality: Modality
  /** Position level in the shared Peru vocabulary (src/peru.ts): title first, then nivelLaboral. */
  level: Level
  employmentType: string | null
}

export { normalizeModality }

export interface JobDetail extends JobCard {
  description: string | null
  seniority: string | null
  category: string | null
  applyUrl: string | null
}

/** Lowercase, strip diacritics, collapse to hyphens — matches Bumeran's own URL slugs. */
export function slugify(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

// ---------------------------------------------------------------------------
// Server-side filters. searchV2 accepts `filtros: [{ id: <facet type>, value:
// <idSemantico> }]`; the response echoes every filter it actually applied in
// `filtersApplied` (by idSemantico). Several values of the same facet are OR'd
// (verified: localidad surco 425 + santiago-de-surco 1554 = 1979 together);
// different facets are AND'd.
// ---------------------------------------------------------------------------

export interface Filtro {
  id: string
  value: string
}

// Region (provincia) idSemanticos, as Bumeran Perú's facet list spells them.
const REGIONS = [
  "amazonas", "ancash", "apurimac", "arequipa", "ayacucho", "cajamarca", "cuzco",
  "huancavelica", "huanuco", "ica", "junin", "la-libertad", "lambayeque", "lima", "loreto",
  "madre-de-dios", "moquegua", "pasco", "piura", "puno", "san-martin", "tacna", "tumbes",
  "ucayali",
]
const REGION_ALIASES: Record<string, string> = { cusco: "cuzco" }

// Lima district localidades. Bumeran derives these from employer-typed text, so one
// district can have several slugs; all are sent (OR'd). Taken from the live localidad
// facet list under provincia=peru|lima (October 2026).
const LIMA_DISTRICT_VARIANTS: Record<string, string[]> = {
  ate: ["ate", "ate-vitarte"],
  "santiago-de-surco": ["santiago-de-surco", "surco", "dpto-401-santiago-de-surco", "urb-higuereta-santiago-de-surco"],
  "magdalena-del-mar": ["magdalena-del-mar", "magdalena"],
  "san-martin-de-porres": ["san-martin-de-porres", "san-martin-de-porres-lima"],
  "san-luis": ["san-luis", "distrito-de-san-luis"],
  "cercado-de-lima": ["cercado-de-lima", "lima"],
  lurigancho: ["lurigancho", "chosica-lurigancho", "chosica"],
  "punta-hermosa": ["punta-hermosa", "distrito-de-punta-hermosa"],
  cieneguilla: ["cieneguilla", "distrito-de-cieneguilla"],
  "san-miguel": ["san-miguel", "urb-maranga-san-miguel"],
  "santa-anita": ["santa-anita", "santa-anima-lima"],
  // Callao postings are mostly filed under provincia Lima on Bumeran Perú.
  callao: ["callao", "ventanilla", "la-perla", "bellavista", "la-punta"],
}
const DISTRICT_ALIASES: Record<string, string> = {
  surco: "santiago-de-surco",
  magdalena: "magdalena-del-mar",
  sjl: "san-juan-de-lurigancho",
  sjm: "san-juan-de-miraflores",
  smp: "san-martin-de-porres",
  ves: "villa-el-salvador",
  vmt: "villa-maria-del-triunfo",
  "lima-cercado": "cercado-de-lima",
  cercado: "cercado-de-lima",
  chosica: "lurigancho",
  "ate-vitarte": "ate",
}

/**
 * Turn a --location value into server-side filtros:
 *   "Lima", "Arequipa", "Cusco"          -> provincia peru|<region>
 *   "San Isidro", "SJL", "Surco", "Callao" -> localidad peru|lima|<district> (+ variants)
 *   "Piura en Sullana"                     -> localidad peru|piura|sullana
 */
export function locationFiltros(location: string): Filtro[] {
  const slug = slugify(location)
  if (!slug) return []
  const nested = slug.match(/^(.+?)-en-(.+)$/)
  if (nested) {
    const region = REGION_ALIASES[nested[1]] ?? nested[1]
    return [{ id: "localidad", value: `peru|${region}|${nested[2]}` }]
  }
  const region = REGION_ALIASES[slug] ?? slug
  if (REGIONS.includes(region)) return [{ id: "provincia", value: `peru|${region}` }]
  const district = DISTRICT_ALIASES[slug] ?? slug
  const variants = LIMA_DISTRICT_VARIANTS[district] ?? [district]
  return variants.map((v) => ({ id: "localidad", value: `peru|lima|${v}` }))
}

const WORK_MODES: Record<string, string> = { remote: "remoto", hybrid: "hibrido", onsite: "presencial" }

export function workModeFiltro(mode: string): Filtro | null {
  const value = WORK_MODES[mode]
  return value ? { id: "modalidad_trabajo", value } : null
}

// Posting-age buckets the API offers (dias_fecha_publicacion idSemanticos).
const AGE_BUCKETS: Array<[number, string]> = [
  [1, "publicacion-hoy"],
  [2, "publicacion-menor-a-2-dias"],
  [3, "publicacion-menor-a-3-dias"],
  [4, "publicacion-menor-a-4-dias"],
  [5, "publicacion-menor-a-5-dias"],
  [6, "publicacion-menor-a-6-dias"],
  [7, "publicacion-menor-a-7-dias"],
  [15, "publicacion-menor-a-15-dias"],
  [30, "publicacion-menor-a-1-mes"],
]

/**
 * Smallest server-side age bucket that still contains every posting <= `days` old, or
 * null when `days` exceeds the largest bucket. The caller still filters client-side on
 * the exact date, since a bucket can be wider than the requested window.
 */
export function ageFiltro(days: number): Filtro | null {
  for (const [max, value] of AGE_BUCKETS) {
    if (days <= max) return { id: "dias_fecha_publicacion", value }
  }
  return null
}

export const LEVELS = [
  "sin-experiencia", "trainee-pasante", "junior", "semi-sr", "senior",
  "senior-semi-senior", "jefe-supervisor-responsable", "otro",
]

export function levelFiltro(level: string): Filtro | null {
  return LEVELS.includes(level) ? { id: "nivel_laboral", value: level } : null
}

/** Requested filtros the API did not echo back in `filtersApplied` (i.e. unrecognized). */
export function unappliedFiltros(
  requested: Filtro[],
  applied: Array<{ idSemantico?: string; value?: string }> | undefined,
): Filtro[] {
  const echoed = new Set((applied ?? []).map((a) => a.idSemantico ?? a.value))
  return requested.filter((f) => !echoed.has(f.value))
}

/** `titulo` + `empresa` + `id` reproduce Bumeran's real seoFriendlyUrl (verified live). */
export function buildResultUrl(id: string, titulo: string, empresa: string | null): string {
  const parts = [slugify(titulo)]
  if (empresa) {
    const companySlug = slugify(empresa)
    if (companySlug) parts.push(companySlug)
  }
  parts.push(id)
  return `${BASE_URL}/empleos/${parts.join("-")}.html`
}

/** Bumeran dates are `DD-MM-YYYY`. Convert to ISO `YYYY-MM-DD`; null if unparseable. */
export function normalizeDate(raw: string | null | undefined): string | null {
  if (!raw) return null
  const m = raw.trim().match(/^(\d{2})-(\d{2})-(\d{4})/)
  if (!m) return null
  return `${m[3]}-${m[2]}-${m[1]}`
}

/** Whole days between an ISO date (YYYY-MM-DD) and now, or null if unparseable. */
export function daysSince(iso: string | null, now: Date = new Date()): number | null {
  if (!iso) return null
  const then = Date.parse(iso + "T00:00:00Z")
  if (isNaN(then)) return null
  const todayUTC = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return Math.round((todayUTC - then) / 86400000)
}

/** Extract a numeric Bumeran aviso id from a bare id, a full job URL, or "aviso-<id>" style input. */
export function normalizeId(input: string): string | null {
  const trimmed = input.trim()
  const fromUrl = trimmed.match(/-(\d{6,})(?:\.html)?(?:[?#].*)?$/)
  if (fromUrl) return fromUrl[1]
  const bare = trimmed.match(/^\d{6,}$/)
  if (bare) return trimmed
  const anyDigits = trimmed.match(/(\d{6,})/)
  return anyDigits ? anyDigits[1] : null
}

function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

// Spanish rich-text descriptions sometimes use named entities for accented characters.
const NAMED_ENTITIES: Record<string, string> = {
  aacute: "á", eacute: "é", iacute: "í", oacute: "ó", uacute: "ú",
  Aacute: "Á", Eacute: "É", Iacute: "Í", Oacute: "Ó", Uacute: "Ú",
  agrave: "à", egrave: "è", igrave: "ì", ograve: "ò", ugrave: "ù",
  auml: "ä", euml: "ë", iuml: "ï", ouml: "ö", uuml: "ü",
  Uuml: "Ü", Ouml: "Ö", Auml: "Ä",
  ntilde: "ñ", Ntilde: "Ñ",
  ccedil: "ç", Ccedil: "Ç",
  iexcl: "¡", iquest: "¿",
  ordf: "ª", ordm: "º",
  bull: "•", middot: "·", ndash: "–", mdash: "—", hellip: "…",
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16)))
    .replace(/&([A-Za-z]+);/g, (m, name) => NAMED_ENTITIES[name] ?? m)
    .replace(/&nbsp;/g, " ")
}

/** Strip tags/decode entities from `descripcion`'s HTML, keeping block-level breaks as newlines. */
export function cleanDescriptionHtml(html: string | null | undefined): string | null {
  if (!html) return null
  const withBreaks = html
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|ul|ol|div|h\d)>/gi, "\n")
  const text = decodeHtmlEntities(withBreaks.replace(/<[^>]+>/g, " "))
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
  return text || null
}

/** Search-result item shape from POST /api/avisos/searchV2. */
export interface RawSearchItem {
  id: number
  titulo: string
  empresa: string | null
  confidencial?: boolean
  localizacion: string | null
  fechaPublicacion: string | null
  modalidadTrabajo?: string | null
  tipoTrabajo?: string | null
}

export interface RawSearchResponse {
  total: number
  content: RawSearchItem[]
  filtersApplied?: Array<{ idSemantico?: string; value?: string }>
}

export function mapSearchItem(item: RawSearchItem): JobCard {
  const id = String(item.id)
  // Confidential postings carry the literal company "Confidencial"; Bumeran's own
  // seoFriendlyUrl omits the company segment for them (verified live).
  const company = item.empresa || null
  return {
    id,
    title: item.titulo,
    company,
    companyUrl: null,
    location: item.localizacion || null,
    date: normalizeDate(item.fechaPublicacion),
    url: buildResultUrl(id, item.titulo, item.confidencial ? null : company),
    workMode: item.modalidadTrabajo || null,
    modality: normalizeModality(item.modalidadTrabajo),
    level: classifyLevel(item.titulo),
    employmentType: item.tipoTrabajo || null,
  }
}

/** `aviso` object shape from GET /api/candidates/fichaAvisoNormalizada/<id>. */
export interface RawAvisoDetail {
  id: number
  titulo: string
  descripcion: string | null
  empresa?: { denominacion?: string | null } | null
  localizacion?: { detalle?: string | null } | null
  fechaPublicacion?: string | null
  tipoTrabajo?: { nombre?: string | null } | null
  modalidadTrabajo?: { nombre?: string | null } | null
  nivelLaboral?: { nombre?: string | null } | null
  area?: { nombre?: string | null } | null
  subArea?: { nombre?: string | null } | null
  redireccionURL?: string | null
  seoFriendlyUrl?: string | null
}

export function mapAvisoDetail(aviso: RawAvisoDetail): JobDetail {
  const id = String(aviso.id)
  const company = aviso.empresa?.denominacion || null
  const category = aviso.subArea?.nombre || aviso.area?.nombre || null
  return {
    id,
    title: aviso.titulo,
    company,
    companyUrl: null,
    location: aviso.localizacion?.detalle || null,
    date: normalizeDate(aviso.fechaPublicacion),
    url: aviso.seoFriendlyUrl ? `${BASE_URL}${aviso.seoFriendlyUrl}` : buildResultUrl(id, aviso.titulo, company),
    workMode: aviso.modalidadTrabajo?.nombre || null,
    modality: normalizeModality(aviso.modalidadTrabajo?.nombre),
    level: classifyLevel(aviso.titulo, aviso.nivelLaboral?.nombre),
    employmentType: aviso.tipoTrabajo?.nombre || null,
    description: cleanDescriptionHtml(aviso.descripcion),
    seniority: aviso.nivelLaboral?.nombre || null,
    category,
    applyUrl: aviso.redireccionURL || null,
  }
}

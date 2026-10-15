// Data source: pe.computrabajo.com (Computrabajo Perú), public server-rendered pages.
// No authentication, no JSON API — a plain fetch of the search/detail pages returns
// full HTML with real content. Search is done via path segments, not a query string:
//   /trabajo-de-<query-slug>                       - keyword search
//   /empleos-en-<location-slug>                     - location only (departamento, or
//                                                      "<departamento>-en-<distrito>")
//   /trabajo-de-<query-slug>-en-<location-slug>      - combined (canonical, the same
//                                                      URLs the site's sidebar links build)
//   /trabajo-de-<query-slug>-en-remoto               - remote-only filter
//   /trabajo-de-<query-slug>-hibrido                 - hybrid filter
// See ../url-reference.md for the full endpoint map, the robots.txt analysis (pubdate=
// is a real but disallowed param, hence --jobage is client-side only), and the detail-page
// not-found quirk (nonexistent IDs 301-redirect to a search page rather than 404ing).
//
// Adapted from the Computrabajo Argentina skill in the GabrielMensi/ai-job-search fork
// (same platform, same markup); re-verified live against pe.computrabajo.com, switched
// to an honest tool-naming User-Agent, and extended with Peru-specific location slugs
// and tag vocabulary.
//
// Both search-result cards and detail pages are parsed with chunked regex — the markup
// is server-rendered and stable enough that a full DOM parser is unnecessary, matching
// the zero-dependency approach used by the other portal skills in this repo (see
// linkedin-search/cli/src/helpers.ts).

import { classifyLevel, normalizeModality, type Level, type Modality } from "./peru.js"

export const BASE_URL = "https://pe.computrabajo.com"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

// Honest, tool-naming UA per the add-portal contract (never a browser impersonation).
// Verified live: pe.computrabajo.com serves full search and detail pages to it.
const UA = "Mozilla/5.0 (compatible; computrabajo-cli/1.0)"

/**
 * Fetch with exponential backoff on 429/5xx. Returns the raw `Response` (not yet
 * read) so callers can inspect status/URL before consuming the body; returns `null`
 * on a genuine 404.
 */
async function fetchWithBackoff(url: string): Promise<Response | null> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
    })
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`)
      }
      const jitter = Math.floor(Math.random() * 500)
      await new Promise((r) => setTimeout(r, delay + jitter))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`)
    }
    return response
  }
  throw new Error("Request failed after max retries")
}

/** Fetch HTML with backoff. Returns "" on a 404 rather than throwing. */
export async function htmlFetch(url: string): Promise<string> {
  const res = await fetchWithBackoff(url)
  return res ? res.text() : ""
}

/**
 * Fetch a job-detail page by ID. Computrabajo tolerates a wrong/placeholder slug as
 * long as the trailing ID is correct, so this always requests the `-x-<id>` form
 * directly. Returns `null` if the job doesn't exist.
 *
 * Nonexistent IDs don't 404 — they 301-redirect to a search-results page instead
 * (e.g. an all-zeros ID redirects to `/trabajo-de-x-000...`, a real search page,
 * HTTP 200). Since `fetch` follows redirects transparently, this checks the final
 * resolved URL: a genuine detail page always stays under `/ofertas-de-trabajo/`.
 */
export async function fetchDetailPage(id: string): Promise<string | null> {
  const url = `${BASE_URL}/ofertas-de-trabajo/oferta-de-trabajo-de-x-${id}`
  const res = await fetchWithBackoff(url)
  if (!res) return null
  if (!res.url.includes("/ofertas-de-trabajo/")) return null
  return res.text()
}

export interface JobCard {
  id: string
  title: string
  company: string | null
  companyUrl: string | null
  location: string | null
  date: string | null
  url: string
  /** Salary chip shown on the card when the employer publishes one, e.g. "S/. 3.500,00 (Mensual)". */
  salary: string | null
  /** Workplace chip ("Remoto", "Presencial y remoto"); null when the card shows none (on-site). */
  workplaceType: string | null
  /** Work mode in the shared Peru vocabulary (src/peru.ts): presencial | híbrido | remoto | no declarado. */
  modality: Modality
  /** Position level in the shared Peru vocabulary (src/peru.ts), from the title. */
  level: Level
}

/**
 * Work mode from Computrabajo's workplace chip. Computrabajo only tags remote ("Remoto")
 * and hybrid ("Presencial y remoto") postings; an untagged posting is on-site. Checked
 * live (October 2026): of 8 untagged Lima postings, none mentioned remote or hybrid
 * work in its description and one said "presencialmente".
 */
export function modalityFromChip(chip: string | null): Modality {
  return chip ? normalizeModality(chip) : "presencial"
}

export interface JobDetail extends JobCard {
  description: string | null
  salary: string | null
  contractType: string | null
  schedule: string | null
  workplaceType: string | null
  requirements: string[]
  skills: string[]
  applyUrl: string | null
}

/**
 * Convert a Unicode code point to a string. Uses `fromCodePoint` (not
 * `fromCharCode`) so supplementary-plane code points decode correctly, and drops
 * out-of-range values instead of throwing.
 */
function numericEntity(cp: number): string {
  return cp >= 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ""
}

// Computrabajo's Spanish postings mostly use numeric hex entities for accented
// characters (e.g. &#xE9; for é) but a named-entity fallback is included
// defensively, matching getonboard-search's approach for the same language.
const NAMED_ENTITIES: Record<string, string> = {
  aacute: "á", eacute: "é", iacute: "í", oacute: "ó", uacute: "ú",
  Aacute: "Á", Eacute: "É", Iacute: "Í", Oacute: "Ó", Uacute: "Ú",
  ntilde: "ñ", Ntilde: "Ñ",
  uuml: "ü", Uuml: "Ü",
  iexcl: "¡", iquest: "¿",
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
    .replace(/&nbsp;?/g, " ")
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
}

/**
 * Like stripTags, but collapses only horizontal whitespace (spaces/tabs) and
 * preserves `\n` — used for the rich description text, where `<br/>` tags are
 * pre-converted to `\n` and must survive tag-stripping to keep paragraph breaks.
 * (Plain stripTags's `\s+` collapse would otherwise flatten those newlines too.)
 */
function stripTagsKeepNewlines(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .join("\n")
}

function clean(html: string | undefined | null): string | null {
  if (!html) return null
  const text = decodeHtmlEntities(stripTags(html)).replace(/\s+/g, " ").trim()
  return text || null
}

/**
 * Turn free text into a Computrabajo URL slug: lowercase, strip accents, collapse
 * anything non-alphanumeric into single hyphens.
 */
export function slugifyQuery(query: string): string {
  return query
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

// Computrabajo Perú nests districts under their region ("lima-en-san-isidro"); a bare
// district slug ("san-isidro") silently returns a page with zero result cards. These
// are the 43 districts of Lima province and the Callao districts, as Computrabajo
// spells them in its own sidebar links (verified live), so a bare district name can be
// resolved without guessing. "mi-peru" is a top-level slug on the site and is left alone.
const LIMA_DISTRICTS = [
  "ancon", "ate", "barranco", "brena", "carabayllo", "chaclacayo", "chorrillos",
  "cieneguilla", "comas", "el-agustino", "independencia", "jesus-maria", "la-molina",
  "la-victoria", "lince", "los-olivos", "lurigancho", "lurin", "magdalena-del-mar",
  "miraflores", "pachacamac", "pucusana", "pueblo-libre", "puente-piedra",
  "punta-hermosa", "punta-negra", "rimac", "san-bartolo", "san-borja", "san-isidro",
  "san-juan-de-lurigancho", "san-juan-de-miraflores", "san-luis", "san-martin-de-porres",
  "san-miguel", "santa-anita", "santa-maria-del-mar", "santa-rosa", "santiago-de-surco",
  "surco", "surquillo", "villa-el-salvador", "villa-maria-del-triunfo",
]
const CALLAO_DISTRICTS = ["bellavista", "carmen-de-la-legua-reynoso", "la-perla", "la-punta", "ventanilla"]

// Common Lima shorthands -> Computrabajo's district slug.
const DISTRICT_ALIASES: Record<string, string> = {
  sjl: "san-juan-de-lurigancho",
  sjm: "san-juan-de-miraflores",
  smp: "san-martin-de-porres",
  ves: "villa-el-salvador",
  vmt: "villa-maria-del-triunfo",
  magdalena: "magdalena-del-mar",
  "cercado-de-lima": "lima",
  "lima-cercado": "lima",
}

/**
 * Turn a --location value into Computrabajo's location slug. Region names
 * ("Lima", "Arequipa", "La Libertad") and already-nested forms ("Lima en San Isidro")
 * pass through slugified; a bare Lima/Callao district name or shorthand is nested
 * under its region ("San Isidro" -> "lima-en-san-isidro", "SJL" ->
 * "lima-en-san-juan-de-lurigancho", "Ventanilla" -> "callao-en-ventanilla").
 */
export function resolveLocationSlug(location: string): string {
  const slug = slugifyQuery(location)
  if (slug.includes("-en-")) return slug
  const aliased = DISTRICT_ALIASES[slug]
  if (aliased === "lima") return "lima-en-lima"
  const district = aliased ?? slug
  if (LIMA_DISTRICTS.includes(district)) return `lima-en-${district}`
  if (CALLAO_DISTRICTS.includes(district)) return `callao-en-${district}`
  return slug
}

/** A Computrabajo job ID: a ~32-char uppercase hex-like string. */
const ID_RE = /^[0-9A-Fa-f]{20,40}$/

/** Accept a bare job ID or a full computrabajo.com job URL; return the ID. */
export function normalizeId(input: string): string | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  if (ID_RE.test(trimmed)) return trimmed.toUpperCase()
  const m = trimmed.match(/-([0-9A-Fa-f]{20,40})(?:[?#]|$)/)
  return m ? m[1].toUpperCase() : null
}

const MONTHS_ES: Record<string, number> = {
  enero: 0, febrero: 1, marzo: 2, abril: 3, mayo: 4, junio: 5,
  julio: 6, agosto: 7, septiembre: 8, setiembre: 8, octubre: 9,
  noviembre: 10, diciembre: 11,
}

/**
 * Computrabajo never shows an absolute date on search cards or detail pages —
 * only relative Spanish phrases: "Hoy", "Ayer", "Hace N horas/días/semanas/meses",
 * or "D de <mes>" for older postings (year-less, same problem getonboard-search
 * solves with normalizeShortDate). Detail pages sometimes suffix "(actualizada)"
 * ("updated"), stripped before parsing. Returns an ISO YYYY-MM-DD date, or null if
 * the phrase doesn't match any known pattern.
 */
export function normalizeRelativeDate(text: string | null, now: Date = new Date()): string | null {
  if (!text) return null
  const t = text
    .replace(/\(actualizada\)/gi, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
  if (!t) return null

  const todayUTC = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  const daysAgoISO = (n: number) => new Date(todayUTC - n * 86400000).toISOString().slice(0, 10)

  if (t === "hoy") return daysAgoISO(0)
  if (t === "ayer") return daysAgoISO(1)

  let m = t.match(/^hace\s+\d+\s+hora/)
  if (m) return daysAgoISO(0)

  m = t.match(/^hace\s+(\d+)\s+d[ií]a/)
  if (m) return daysAgoISO(parseInt(m[1], 10))

  m = t.match(/^hace\s+(\d+)\s+semana/)
  if (m) return daysAgoISO(parseInt(m[1], 10) * 7)

  m = t.match(/^hace\s+(\d+)\s+mes/)
  if (m) return daysAgoISO(parseInt(m[1], 10) * 30)

  m = t.match(/^(\d{1,2})\s+de\s+([a-zñ]+)$/)
  if (m) {
    const day = parseInt(m[1], 10)
    const month = MONTHS_ES[m[2]]
    if (month === undefined || day < 1 || day > 31) return null
    let year = now.getUTCFullYear()
    let candidate = Date.UTC(year, month, day)
    if (candidate > todayUTC) {
      year -= 1
      candidate = Date.UTC(year, month, day)
    }
    return new Date(candidate).toISOString().slice(0, 10)
  }

  return null
}

/** Whole days between an ISO date (YYYY-MM-DD) and `now`, or null if unparseable. */
export function daysSince(iso: string | null, now: Date = new Date()): number | null {
  if (!iso) return null
  const then = Date.parse(iso + "T00:00:00Z")
  if (isNaN(then)) return null
  const todayUTC = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return Math.round((todayUTC - then) / 86400000)
}

/** Parse the real total-result count from the search page's <h1> badge, if present. */
export function parseTotalResults(html: string): number | null {
  const m = html.match(/<h1[^>]*>\s*<span class="fwB">\s*([\d.,]+)\s*<\/span>/)
  if (!m) return null
  const n = parseInt(m[1].replace(/[.,]/g, ""), 10)
  return isNaN(n) ? null : n
}

/**
 * Parse a search-results page: a flat list of `<article class="box_offer ...">`
 * cards. Each chunk is bounded from one card's marker to the start of the next (or
 * end of string), so a missing/malformed field in one card cannot leak into, or be
 * polluted by, its neighbor.
 */
export function parseJobCards(html: string, now: Date = new Date()): JobCard[] {
  const marker = '<article class="box_offer'
  const starts: number[] = []
  let i = html.indexOf(marker)
  while (i !== -1) {
    starts.push(i)
    i = html.indexOf(marker, i + marker.length)
  }

  const results: JobCard[] = []
  for (let k = 0; k < starts.length; k++) {
    const chunk = html.slice(starts[k], starts[k + 1] ?? html.length)
    const card = parseOneCard(chunk, now)
    if (card) results.push(card)
  }
  return results
}

function parseOneCard(chunk: string, now: Date): JobCard | null {
  const idMatch = chunk.match(/data-id='([^']+)'/)
  if (!idMatch) return null
  const id = idMatch[1].toUpperCase()

  const titleMatch = chunk.match(
    /class="js-o-link fc_base" href="([^"]+)">\s*([\s\S]*?)\s*<\/a>/,
  )
  if (!titleMatch) return null
  const url = new URL(decodeHtmlEntities(titleMatch[1]).split("#")[0], BASE_URL).toString()
  const title = clean(titleMatch[2])
  if (!title) return null

  // Company: two markup shapes — plain text, or an <a ... offer-grid-article-company-url>
  // link, which is often preceded by a rating (e.g. "4,2") and a verified-badge icon
  // sharing the same <p>. When the link is present, take the company name from the
  // link text alone (not the whole paragraph) or the rating number leaks into it.
  let company: string | null = null
  let companyUrl: string | null = null
  const pMatch = chunk.match(/<p class="dFlex vm_fx fs16 fc_base mt5">([\s\S]*?)<\/p>/)
  if (pMatch) {
    const linkMatch = pMatch[1].match(
      /href="([^"]+)"[^>]*offer-grid-article-company-url[^>]*>([\s\S]*?)<\/a>/,
    )
    if (linkMatch) {
      company = clean(linkMatch[2])
      companyUrl = new URL(decodeHtmlEntities(linkMatch[1]), BASE_URL).toString()
    } else {
      company = clean(pMatch[1])
    }
  }

  const locMatch = chunk.match(/<p class="fs16 fc_base mt5">\s*<span class="mr10">\s*([\s\S]*?)\s*<\/span>/)
  const location = locMatch ? clean(locMatch[1]) : null

  const dateMatch = chunk.match(/<p class="fs13 fc_aux mt15">\s*([\s\S]*?)\s*<\/p>/)
  const date = normalizeRelativeDate(dateMatch ? clean(dateMatch[1]) : null, now)

  // Optional chips in <div class="fs13 mt15">, each an icon span followed by text:
  // i_salary -> published salary, i_home / i_home_office -> remote / hybrid.
  const salaryMatch = chunk.match(/<span class="icon i_salary"><\/span>\s*([\s\S]*?)\s*<\/span>/)
  const salary = salaryMatch ? clean(salaryMatch[1]) : null
  const workMatch = chunk.match(/<span class="icon i_home(?:_office)?"><\/span>\s*([\s\S]*?)\s*<\/span>/)
  const workplaceType = workMatch ? clean(workMatch[1]) : null

  return { id, title, company, companyUrl, location, date, url, salary, workplaceType, modality: modalityFromChip(workplaceType), level: classifyLevel(title) }
}

/** Classify tag chips (salary / contract type / schedule / workplace) by keyword. */
function classifyTags(tags: string[]): {
  salary: string | null
  contractType: string | null
  schedule: string | null
  workplaceType: string | null
} {
  let salary: string | null = null
  let contractType: string | null = null
  let schedule: string | null = null
  let workplaceType: string | null = null
  // Peru chips observed live: "Tiempo completo", "Medio tiempo", "Contrato a Plazo
  // Indeterminado", "Presencial y remoto", "A convenir" / "S/. 3.500,00 (Mensual)".
  for (const tag of tags) {
    const low = tag.toLowerCase()
    if (/jornada|tiempo completo|medio tiempo|tiempo parcial|por horas|turno/.test(low)) schedule = tag
    else if (
      /contrato|indeterminado|plazo fijo|eventual|pasant[ií]a|pr[aá]cticas|locaci[oó]n|honorarios|freelance|temporal|temporada|obra/.test(low)
    )
      contractType = tag
    else if (/remoto|presencial|h[ií]brido/.test(low)) workplaceType = tag
    else if (salary === null) salary = tag
  }
  return { salary, contractType, schedule, workplaceType }
}

/** Parse a single job's detail page. */
export function parseJobDetail(html: string, id: string, now: Date = new Date()): JobDetail {
  const title = clean(html.match(/<h1 class="fwB fs24 mb5 box_detail w100_m">([\s\S]*?)<\/h1>/)?.[1]) ?? "(untitled)"

  // "COMPANY - LOCATION" — split on the LAST " - " (company names can themselves
  // contain hyphens; location is always the trailing segment). Company may
  // legitimately be the literal placeholder "Importante empresa del sector" when
  // the employer stays anonymous — passed through as-is, not treated as null.
  const headerMatch = html.match(/<\/h1>\s*<p class="fs16">([\s\S]*?)<\/p>/)
  let company: string | null = null
  let location: string | null = null
  if (headerMatch) {
    const headerText = clean(headerMatch[1]) ?? ""
    const idx = headerText.lastIndexOf(" - ")
    if (idx !== -1) {
      company = headerText.slice(0, idx).trim() || null
      location = headerText.slice(idx + 3).trim() || null
    } else {
      location = headerText || null
    }
  }

  // Only present for named/linked companies — the whole block is absent for
  // anonymized ("Importante empresa del sector") postings.
  const companyLinkMatch = html.match(
    /class="info_company[^"]*"[\s\S]*?<a class="dIB fs16 js-o-link" href="([^"]+)"[^>]*>/,
  )
  const companyUrl = companyLinkMatch ? new URL(decodeHtmlEntities(companyLinkMatch[1]), BASE_URL).toString() : null

  // Tag chips (salary / contract / schedule / workplace) right after the
  // "Descripción de la oferta" heading.
  // The heading is an <h3> on some Peru detail pages and an <h2> on others
  // (both seen live, October 2026); missing the <h2> form silently dropped every chip.
  const tagsBlockMatch = html.match(/de la oferta<\/h[23]>\s*<div class="mbB">([\s\S]*?)<\/div>/)
  const tags: string[] = []
  if (tagsBlockMatch) {
    const tagRe = /<span class="tag base mb10">([\s\S]*?)<\/span>/g
    let tm: RegExpExecArray | null
    while ((tm = tagRe.exec(tagsBlockMatch[1])) !== null) {
      const t = clean(tm[1])
      if (t) tags.push(t)
    }
  }
  const { salary, contractType, schedule, workplaceType } = classifyTags(tags)

  // Description: a single flat <p class="mbB"> with <br/> line breaks (not nested
  // divs like linkedin-search/getonboard-search parse).
  const descMatch = html.match(/<p class="mbB">([\s\S]*?)<\/p>/)
  let description: string | null = null
  if (descMatch) {
    const withBreaks = descMatch[1].replace(/<\s*br\s*\/?>/gi, "\n")
    description =
      decodeHtmlEntities(stripTagsKeepNewlines(withBreaks)).replace(/\n{3,}/g, "\n\n").trim() || null
  }

  const requirements: string[] = []
  const reqBlockMatch = html.match(/Requerimientos<\/p>\s*<ul class="disc mbB">([\s\S]*?)<\/ul>/)
  if (reqBlockMatch) {
    const liRe = /<li[^>]*>([\s\S]*?)<\/li>/g
    let lm: RegExpExecArray | null
    while ((lm = liRe.exec(reqBlockMatch[1])) !== null) {
      const r = clean(lm[1])
      if (r) requirements.push(r)
    }
  }

  const skills: string[] = []
  const skillRe = /class="tag bg_brand_light fc_base mr5 mt10 big" data-skill-id="[^"]*">([\s\S]*?)<\/span>/g
  let sm: RegExpExecArray | null
  while ((sm = skillRe.exec(html)) !== null) {
    const s = clean(sm[1])
    if (s) skills.push(s)
  }

  const dateMatch = html.match(/<p class="fc_aux fs13">\s*([\s\S]*?)\s*<\/p>/)
  const date = normalizeRelativeDate(dateMatch ? clean(dateMatch[1]) : null, now)

  const applyMatch = html.match(/data-href-offer-apply="([^"]+)"/)
  const applyUrl = applyMatch ? decodeHtmlEntities(applyMatch[1]) : null

  return {
    id,
    title,
    company,
    companyUrl,
    location,
    date,
    url: `${BASE_URL}/ofertas-de-trabajo/oferta-de-trabajo-de-x-${id}`,
    description,
    salary,
    contractType,
    schedule,
    workplaceType,
    modality: modalityFromChip(workplaceType),
    level: classifyLevel(title),
    requirements,
    skills,
    applyUrl,
  }
}

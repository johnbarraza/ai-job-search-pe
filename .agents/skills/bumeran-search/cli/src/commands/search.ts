import {
  ageFiltro,
  apiRequest,
  daysSince,
  levelFiltro,
  locationFiltros,
  mapSearchItem,
  unappliedFiltros,
  workModeFiltro,
  writeError,
  type Filtro,
  type JobCard,
  type RawSearchResponse,
} from "../helpers.js"

export interface SearchOpts {
  query?: string
  location?: string
  remote?: string // "remote" | "hybrid" | "onsite"
  level?: string
  sort: "relevant" | "recent"
  jobage: number // 9999 = no filter
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

const PAGE_SIZE = 20

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const locFiltros = opts.location ? locationFiltros(opts.location) : []
    const otherFiltros: Filtro[] = []
    if (opts.remote) {
      const f = workModeFiltro(opts.remote)
      if (f) otherFiltros.push(f)
    }
    if (opts.level) {
      const f = levelFiltro(opts.level)
      if (f) otherFiltros.push(f)
    }
    if (opts.jobage < 9999) {
      const f = ageFiltro(opts.jobage)
      if (f) otherFiltros.push(f)
    }
    const filtros = [...locFiltros, ...otherFiltros]

    const apiPage = Math.max(0, opts.page - 1)
    const sort = opts.sort === "recent" ? "RECIENTES" : "RELEVANTES"
    const data = await apiRequest<RawSearchResponse>(
      `api/avisos/searchV2?pageSize=${PAGE_SIZE}&page=${apiPage}&sort=${sort}`,
      { method: "POST", body: { filtros, query: opts.query ?? "", internacional: false } },
    )

    // An unrecognized filter value doesn't error: the API returns total 0 and leaves it
    // out of filtersApplied. Surface that instead of reporting "no jobs". Location
    // variants are OR'd, so only fail when none of them was recognized.
    const missing = unappliedFiltros(filtros, data?.filtersApplied)
    if (locFiltros.length && locFiltros.every((f) => missing.some((m) => m.value === f.value))) {
      writeError(
        `location "${opts.location}" was not recognized by Bumeran (tried ${locFiltros
          .map((f) => f.value)
          .join(", ")}). Use a region ("Lima", "Arequipa", "Cusco"), a Lima district ("San Isidro", "SJL"), or "<Region> en <City>" ("Piura en Sullana").`,
        "LOCATION_NOT_FOUND",
      )
      return 1
    }
    const missingOther = missing.filter((m) => otherFiltros.some((f) => f.value === m.value))
    if (missingOther.length) {
      writeError(
        `filter value(s) not recognized by Bumeran: ${missingOther.map((f) => `${f.id}=${f.value}`).join(", ")}`,
        "FILTER_NOT_APPLIED",
      )
      return 1
    }

    let cards: JobCard[] = (data?.content ?? []).map(mapSearchItem)

    // The age bucket can be wider than the requested window (e.g. --jobage 10 uses the
    // 15-day bucket), so trim to the exact window on the full DD-MM-YYYY date.
    if (opts.jobage < 9999) {
      cards = cards.filter((c) => {
        const days = daysSince(c.date)
        return days === null ? true : days <= opts.jobage
      })
    }

    if (opts.limit !== undefined) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}` +
              ` · ${c.modality ?? "modalidad no indicada"}` +
              `\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          { meta: { count: cards.length, page: opts.page, totalResults: data?.total ?? null, filtros }, results: cards },
          null,
          2,
        ) + "\n",
      )
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED")
    return 1
  }
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42)
    const company = (c.company || "—").slice(0, 24).padEnd(24)
    const loc = (c.location || "—").slice(0, 24).padEnd(24)
    const mode = (c.modality || "—").padEnd(10)
    const date = c.date || "—"
    return `${c.id.padEnd(12)} ${title} ${company} ${loc} ${mode} ${date}`
  })
  const header =
    "ID".padEnd(12) + " " + "TITLE".padEnd(42) + " " + "COMPANY".padEnd(24) + " " + "LOCATION".padEnd(24) + " " +
    "MODALIDAD".padEnd(10) + " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

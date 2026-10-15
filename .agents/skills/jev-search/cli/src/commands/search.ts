import {
  buildSearchGoal,
  buildStartUrl,
  defaultRunner,
  findSite,
  jevArgs,
  jevCliPath,
  parseSearchAnswer,
  preflight,
  reportUnfinished,
  runJev,
  writeError,
  type JobCard,
  type Runner,
} from "../helpers.js"

export interface CommonOpts {
  maxSteps: number
  headed: boolean
  timeoutMs: number
}

export interface SearchOpts extends CommonOpts {
  site: string
  query?: string
  location?: string
  url?: string
  limit: number
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobCard[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 40).padEnd(40)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 20).padEnd(20)
    const mode = c.modality.padEnd(12)
    return `${title} ${company} ${loc} ${mode} ${c.level.slice(0, 22).padEnd(22)} ${c.deadline || c.date || "—"}`
  })
  const header =
    "TITLE".padEnd(40) + " " + "COMPANY".padEnd(26) + " " + "LOCATION".padEnd(20) + " " + "MODALIDAD".padEnd(12) +
    " " + "NIVEL".padEnd(22) + " DEADLINE/DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts, run: Runner = defaultRunner): Promise<number> {
  const site = findSite(opts.site)
  if (!site) {
    writeError(`unknown --site "${opts.site}"; run the "sites" command for the list`, "BAD_SITE")
    return 1
  }
  let url: string
  try {
    url = buildStartUrl(site, opts.query, opts.location, opts.url)
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "NO_URL")
    return 1
  }
  const blocked = await preflight(url, run)
  if (blocked !== null) return blocked

  try {
    const goal = buildSearchGoal(site, { query: opts.query, location: opts.location, limit: opts.limit })
    const result = await runJev(
      jevArgs(url, goal, { maxSteps: opts.maxSteps, headed: opts.headed, cli: jevCliPath() }),
      opts.timeoutMs,
      run,
    )
    if (result.status !== "done" || !result.answer) return reportUnfinished(result)
    const cards = parseSearchAnswer(result.answer, site.id, result.final_url ?? url).slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.modality} · ${c.level}` +
              `${c.salary ? ` · ${c.salary}` : ""}${c.deadline ? ` · cierra ${c.deadline}` : ""}\n  id: ${c.id}` +
              `${c.url ? `\n  ${c.url}` : ""}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          {
            meta: {
              count: cards.length,
              page: 1,
              site: site.id,
              startUrl: url,
              finalUrl: result.final_url ?? null,
              steps: result.steps ?? null,
              elapsedMs: result.elapsed_ms ?? null,
            },
            results: cards,
          },
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


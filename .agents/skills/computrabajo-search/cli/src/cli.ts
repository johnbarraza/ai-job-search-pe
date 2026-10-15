#!/usr/bin/env bun
// Self-contained CLI for searching jobs on Computrabajo Perú (pe.computrabajo.com).
// No external CLI framework, so it runs anywhere `bun` is available with zero install
// beyond the repo clone.
//
// Public, server-rendered pages; no login wall and a permissive robots.txt (see
// ../SKILL.md and ../url-reference.md). Keep volume low and do not use this
// commercially or for bulk data collection. Run it on your own responsibility.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", l: "location", n: "limit" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
      const next = argv[i + 1]
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true
      } else {
        flags[key] = next
        i++
      }
    } else {
      ;(flags._ as string[]).push(a)
    }
  }
  return flags
}

const HELP = `computrabajo-cli — search jobs on Computrabajo Perú (pe.computrabajo.com)

USAGE
  bun run src/cli.ts search [--query <text>] [--location <text>] [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Keywords (job title, skill, or role), e.g. "analista de
                          datos", "contador". At least one of --query/--location
                          is required.
  --location, -l <text>   Region (departamento) name, e.g. "Lima", "Arequipa",
                          "La Libertad", "Callao"; or a Lima/Callao district, e.g.
                          "San Isidro", "Miraflores", "SJL" (auto-nested as
                          "lima-en-<district>"); or "<Region> en <City>" for any
                          other city (e.g. "Piura en Sullana"). See SKILL.md.
  --remote <mode>         remote | hybrid. Filter by workplace type ("onsite" is
                          a no-op - see SKILL.md, no such filter exists).
  --jobage <days>         Keep postings normalized to N days old or newer.
                          Best-effort client-side filter - see SKILL.md. Default: all.
  --page <n>              1-indexed page (20 results/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "analista de datos" -l "Lima" --format table
  bun run src/cli.ts search -q "contador" -l "San Isidro" --jobage 7 --format table
  bun run src/cli.ts search -q "desarrollador" --remote remote --format table
  bun run src/cli.ts search -l "Arequipa" --format table
  bun run src/cli.ts detail A1159FCAE890A3F861373E686DCF3405 --format plain

Personal use only — keep volume low (see SKILL.md).
`

// Long-form flag names each command accepts (parseFlags resolves the short aliases
// q/l/n first). Unknown flags are rejected rather than silently ignored: a dropped
// filter changes what the search returns with no error (add-portal.md contract).
const KNOWN_FLAGS: Record<string, Set<string>> = {
  search: new Set(["query", "location", "remote", "jobage", "page", "limit", "format", "help", "h"]),
  detail: new Set(["format", "help", "h"]),
}

function fail(error: string, code: string): number {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
  return 1
}

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  const knownFlags = KNOWN_FLAGS[cmd]
  if (knownFlags) {
    for (const key of Object.keys(flags)) {
      if (key === "_" || knownFlags.has(key)) continue
      return fail(
        `unknown flag --${key} for '${cmd}' - flags are never silently ignored, because a discarded filter changes what the search returns; see --help for the supported flags`,
        "UNKNOWN_FLAG",
      )
    }
  }

  if (cmd === "search") {
    const fmt = flags.format !== undefined ? String(flags.format) : "json"
    if (!["json", "table", "plain"].includes(fmt)) {
      return fail(`--format must be one of json|table|plain, got "${fmt}"`, "BAD_ARG")
    }

    // Whole numbers >= 1 only, matching the other portal CLIs (Number(), not
    // parseInt(), so "0.5" or "7days" is rejected instead of truncated).
    const intFlag = (name: string): number | null | undefined => {
      const raw = flags[name]
      if (raw === undefined) return undefined
      const val = typeof raw === "string" ? Number(raw.trim()) : NaN
      if (!Number.isInteger(val) || val < 1) {
        fail(`--${name} must be a whole number of at least 1, got "${raw}"`, "BAD_ARG")
        return null
      }
      return val
    }
    const jobage = intFlag("jobage")
    if (jobage === null) return 1
    const page = intFlag("page")
    if (page === null) return 1
    const limit = intFlag("limit")
    if (limit === null) return 1

    const remote = typeof flags.remote === "string" ? flags.remote.toLowerCase() : undefined
    if (flags.remote !== undefined && !["remote", "hybrid", "onsite"].includes(remote ?? "")) {
      return fail(`--remote must be one of remote|hybrid|onsite, got "${flags.remote}"`, "BAD_ARG")
    }

    const query = typeof flags.query === "string" ? flags.query : undefined
    const location = typeof flags.location === "string" ? flags.location : undefined
    if (!query && !location) {
      return fail("at least one of --query/-q or --location/-l is required", "NO_QUERY")
    }

    const opts: SearchOpts = {
      query,
      location,
      remote,
      jobage: jobage ?? 9999,
      page: page ?? 1,
      limit,
      format: fmt as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) return fail("detail requires an <id|url>", "NO_ID")
    const fmt = flags.format !== undefined ? String(flags.format) : "json"
    if (!["json", "plain"].includes(fmt)) {
      return fail(`--format must be one of json|plain for detail, got "${fmt}"`, "BAD_ARG")
    }
    const opts: DetailOpts = { id, format: fmt as DetailOpts["format"] }
    return runDetail(opts)
  }

  return fail(`Unknown command "${cmd}"`, "BAD_CMD")
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    process.stderr.write(
      JSON.stringify({
        error: e instanceof Error ? e.message : String(e),
        code: "INTERNAL_ERROR",
      }) + "\n",
    )
    process.exit(1)
  })

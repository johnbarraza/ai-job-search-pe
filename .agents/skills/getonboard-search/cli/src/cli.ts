#!/usr/bin/env bun
// Self-contained CLI for searching jobs on GetOnBoard (getonbrd.com), Latin
// America's tech/startup job board, via its official public REST API. No
// external CLI framework, so it runs anywhere `bun` is available with zero
// install beyond the repo clone.
//
// Data source: https://www.getonbrd.com/api/v0/search/jobs - a documented,
// unauthenticated public endpoint (see ../url-reference.md). Replaces an
// earlier HTML-scraping implementation of this skill.

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

const HELP = `getonboard-cli — search tech/data/startup jobs on GetOnBoard (getonbrd.com) via its public API

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Free-text keyword search (full-text, via the API).
  --location, -l <text>   Country: Peru, Chile, Colombia, Mexico, Argentina, Ecuador,
                          Costa Rica, Spain (or the 2-letter code, e.g. "PE").
                          Country-level only - the API has no city filter. "Peru"
                          also returns remote roles open to candidates in Peru.
  --jobage <days>         Keep postings published within N days (exact timestamps).
  --page <n>              Server-side pagination (50/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "data analyst" -l "Peru" --format table
  bun run src/cli.ts search -q "analista" -l PE --jobage 14 --format table
  bun run src/cli.ts search -l "Peru" --format table
  bun run src/cli.ts detail talana-linq/analista-de-facturacion-talana-lima --format plain

See ../SKILL.md and ../url-reference.md for API notes.
`

// Unknown flags are rejected rather than silently ignored: a dropped filter changes what
// the search returns with no error (add-portal.md contract).
const KNOWN_FLAGS: Record<string, Set<string>> = {
  search: new Set(["query", "location", "jobage", "page", "limit", "format", "help", "h"]),
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

    // Whole numbers >= 1 only (Number(), not parseInt(), so "0.5" or "7days" is rejected).
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

    const opts: SearchOpts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      location: typeof flags.location === "string" ? flags.location : undefined,
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

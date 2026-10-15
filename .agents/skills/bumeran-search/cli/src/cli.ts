#!/usr/bin/env bun
// Self-contained CLI for searching jobs on Bumeran Perú (bumeran.com.pe) via the site's
// own JSON API. No external CLI framework, so it runs anywhere `bun` is available with
// zero install beyond the repo clone.
//
// Personal use only: keep volume low and do not use this commercially or for bulk data
// collection (see ../SKILL.md). Run it on your own responsibility.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"
import { LEVELS } from "./helpers.js"

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

const HELP = `bumeran-cli — search jobs on Bumeran Perú (bumeran.com.pe)

USAGE
  bun run src/cli.ts search [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Keyword search (multi-word works: "analista de datos").
                          Omit for the full listing narrowed by the other filters.
  --location, -l <text>   Server-side location filter: a region ("Lima", "Arequipa",
                          "Cusco"), a Lima district ("San Isidro", "Miraflores", "SJL",
                          "Surco", "Callao"), or "<Region> en <City>" ("Piura en Sullana").
  --remote <mode>         remote | hybrid | onsite (server-side work-mode filter).
  --level <level>         Server-side seniority filter: ${LEVELS.join(" | ")}.
  --jobage <days>         Posted within N days (server-side bucket + exact client-side trim).
  --sort <order>          relevant (default) | recent.
  --page <n>              1-indexed page (20 results/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "analista de datos" -l "Lima" --jobage 7 --format table
  bun run src/cli.ts search -q "practicante" -l "San Isidro" --format table
  bun run src/cli.ts search -q "economista" --remote hybrid --level junior --format table
  bun run src/cli.ts search -q "contador" -l "Arequipa" --sort recent --format table
  bun run src/cli.ts detail 1118483020 --format plain

Personal use only — keep volume low (see SKILL.md).
`

// Unknown flags are rejected rather than silently ignored: a dropped filter changes what
// the search returns with no error (add-portal.md contract).
const KNOWN_FLAGS: Record<string, Set<string>> = {
  search: new Set(["query", "location", "remote", "level", "jobage", "sort", "page", "limit", "format", "help", "h"]),
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

    const str = (name: string): string | undefined =>
      typeof flags[name] === "string" ? (flags[name] as string).trim() : undefined

    const remote = str("remote")?.toLowerCase()
    if (flags.remote !== undefined && !["remote", "hybrid", "onsite"].includes(remote ?? "")) {
      return fail(`--remote must be one of remote|hybrid|onsite, got "${flags.remote}"`, "BAD_ARG")
    }
    const level = str("level")?.toLowerCase()
    if (flags.level !== undefined && !LEVELS.includes(level ?? "")) {
      return fail(`--level must be one of ${LEVELS.join("|")}, got "${flags.level}"`, "BAD_ARG")
    }
    const sort = str("sort")?.toLowerCase() ?? "relevant"
    if (!["relevant", "recent"].includes(sort)) {
      return fail(`--sort must be one of relevant|recent, got "${flags.sort}"`, "BAD_ARG")
    }
    if (flags.query !== undefined && typeof flags.query !== "string") {
      return fail("--query needs a value", "BAD_ARG")
    }
    if (flags.location !== undefined && !str("location")) {
      return fail("--location needs a value", "BAD_ARG")
    }

    const opts: SearchOpts = {
      query: str("query"),
      location: str("location"),
      remote,
      level,
      sort: sort as SearchOpts["sort"],
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

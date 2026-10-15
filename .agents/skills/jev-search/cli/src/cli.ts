#!/usr/bin/env bun
// jev-search: read Peruvian job boards that a plain fetch cannot (Talento Perú, Laborum,
// Empleos Perú, Prácticas.pe, a university bolsa) by driving Chrome with jev-browse, which
// is vendored as a git submodule at vendor/jev-browse. See ../SKILL.md: every run makes
// paid model calls and sends page text to the model providers.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"
import { SITES } from "./helpers.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", l: "location", n: "limit", s: "site" }
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

const HELP = `jev-search — read Peruvian job boards through a real browser driven by jev-browse

USAGE
  bun run src/cli.ts sites
  bun run src/cli.ts search --site <id> [--query <text>] [--location <text>] [flags]
  bun run src/cli.ts detail <url> [--format json|plain] [flags]

SITES
${SITES.map((s) => `  ${s.id.padEnd(12)} ${s.name}`).join("\n")}

SEARCH FLAGS
  --site, -s <id>        Board to search (see SITES). Required.
  --query, -q <text>     Search terms, e.g. "practicante economía".
  --location, -l <text>  Departamento or city, e.g. "Lima".
  --url <url>            Start URL: required for --site url, optional override otherwise.
  --limit, -n <n>        Max postings to read (default 15, max 30).
  --format <fmt>         json (default) | table | plain.

COMMON FLAGS
  --max-steps <n>        jev-browse action budget (default 40, max 80).
  --timeout <seconds>    Hard stop for the whole run (default 300).
  --headed               Show the Chrome window.

Needs: git submodule vendor/jev-browse, Node 22+, Chrome, and model keys
(TYPESAFE_API_KEY or OPENROUTER_API_KEY, plus TEXT_MODEL_API_KEY). Every run is
robots.txt-gated, read-only, stops at any CAPTCHA, and makes paid model calls.
`

const KNOWN_FLAGS: Record<string, Set<string>> = {
  sites: new Set(["format", "help", "h"]),
  search: new Set([
    "site", "query", "location", "url", "limit", "format", "max-steps", "timeout", "headed", "help", "h",
  ]),
  detail: new Set(["format", "max-steps", "timeout", "headed", "help", "h"]),
}

function fail(error: string, code: string): number {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
  return 1
}

async function main(): Promise<number> {
  const flags = parseFlags(process.argv.slice(2))
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  const knownFlags = KNOWN_FLAGS[cmd]
  if (!knownFlags) return fail(`Unknown command "${cmd}"`, "BAD_CMD")
  for (const key of Object.keys(flags)) {
    if (key === "_" || knownFlags.has(key)) continue
    return fail(
      `unknown flag --${key} for '${cmd}' - flags are never silently ignored, because a discarded filter changes what the search returns; see --help for the supported flags`,
      "UNKNOWN_FLAG",
    )
  }

  if (cmd === "sites") {
    process.stdout.write(
      JSON.stringify({ sites: SITES.map(({ id, name, url, notes }) => ({ id, name, url, notes })) }, null, 2) + "\n",
    )
    return 0
  }

  const intFlag = (name: string, dflt: number, max: number): number | null => {
    const raw = flags[name]
    if (raw === undefined) return dflt
    const val = typeof raw === "string" ? Number(raw.trim()) : NaN
    if (!Number.isInteger(val) || val < 1 || val > max) {
      fail(`--${name} must be a whole number from 1 to ${max}, got "${raw}"`, "BAD_ARG")
      return null
    }
    return val
  }
  const maxSteps = intFlag("max-steps", 40, 80)
  if (maxSteps === null) return 1
  const timeout = intFlag("timeout", 300, 1800)
  if (timeout === null) return 1
  const headed = flags.headed === true
  if (flags.headed !== undefined && flags.headed !== true) return fail("--headed takes no value", "BAD_ARG")

  const httpUrl = (raw: unknown): string | null => {
    if (typeof raw !== "string") return null
    try {
      const u = new URL(raw)
      return u.protocol === "http:" || u.protocol === "https:" ? u.toString() : null
    } catch {
      return null
    }
  }

  if (cmd === "search") {
    const fmt = flags.format !== undefined ? String(flags.format) : "json"
    if (!["json", "table", "plain"].includes(fmt)) return fail(`--format must be one of json|table|plain, got "${fmt}"`, "BAD_ARG")
    if (typeof flags.site !== "string") return fail("--site is required; run the \"sites\" command for the list", "NO_SITE")
    const limit = intFlag("limit", 15, 30)
    if (limit === null) return 1
    let url: string | undefined
    if (flags.url !== undefined) {
      const parsed = httpUrl(flags.url)
      if (!parsed) return fail(`--url must be an http(s) URL, got "${flags.url}"`, "BAD_ARG")
      url = parsed
    }
    const opts: SearchOpts = {
      site: flags.site,
      query: typeof flags.query === "string" ? flags.query : undefined,
      location: typeof flags.location === "string" ? flags.location : undefined,
      url,
      limit,
      format: fmt as SearchOpts["format"],
      maxSteps,
      headed,
      timeoutMs: timeout * 1000,
    }
    return runSearch(opts)
  }

  // detail
  const url = httpUrl((flags._ as string[])[1])
  if (!url) return fail("detail requires an http(s) <url>", "NO_URL")
  const fmt = flags.format !== undefined ? String(flags.format) : "json"
  if (!["json", "plain"].includes(fmt)) return fail(`--format must be one of json|plain for detail, got "${fmt}"`, "BAD_ARG")
  const opts: DetailOpts = { url, format: fmt as DetailOpts["format"], maxSteps, headed, timeoutMs: timeout * 1000 }
  return runDetail(opts)
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    process.stderr.write(
      JSON.stringify({ error: e instanceof Error ? e.message : String(e), code: "INTERNAL_ERROR" }) + "\n",
    )
    process.exit(1)
  })

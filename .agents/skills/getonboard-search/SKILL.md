---
name: getonboard-search
version: 1.2.0
description: >
  Use this skill to search tech, data, analytics and startup jobs in Peru and Latin
  America (Peru, Chile, Colombia, Mexico, Argentina, Ecuador, Costa Rica, Spain) through
  GetOnBoard's official public API, including remote roles open to candidates in Peru, or
  to look up a specific getonbrd.com posting. Strongest for software, data analysis, BI,
  data science, product, and startup operations roles. Trigger phrases include:
  GetOnBoard, Get on Board, getonbrd, empleos tech Perú, trabajo remoto, analista de
  datos, data analyst Lima, data scientist Perú, desarrollador, startups Lima, tech jobs
  latam, remote jobs latin america, jobs Peru, jobs Lima, find a job, job search, job
  openings, hiring.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/getonboard-search/cli/src/cli.ts *)
---

# GetOnBoard Search Skill

Search live listings from **GetOnBoard** (getonbrd.com), Latin America's main tech and
startup job board, through its **official public REST API** (`GET /api/v0/search/jobs`,
documented at https://www.getonbrd.com/api-doc.html). No authentication, no API key,
**zero runtime dependencies**: it runs with just `bun`. Postings are mostly in Spanish.

> Adapted from the GetOnBoard skill in the
> [GabrielMensi/ai-job-search](https://github.com/GabrielMensi/ai-job-search) fork, with
> Peru as the documented default market and an honest tool-naming User-Agent (the
> original sent a browser UA; see "Access notes").

## Why it matters for Peru

`-l Peru` (country_code `PE`) returns both roles located in Peru and **remote roles open to
candidates in Peru** (`remote_local` postings whose `countries` list Peru): verified live
in October 2026, a `python` search with `PE` returned Lima-hybrid roles alongside remote
roles from Chilean and regional companies. It is the best structured source in this fork
for data/analytics and tech-adjacent roles; for banking, consulting, and general
corporate roles use `bumeran-search`, `computrabajo-search`, and `linkedin-search`.

## Access notes

As of 2026-10-15, `https://www.getonbrd.com/robots.txt` contains only a comment and no
rules (fetched with the CLI's UA, a browser UA, and a `ClaudeBot` UA: same 99-byte file).
The original fork documented an earlier version that disallowed named AI crawlers
(`ClaudeBot`, `GPTBot`, `CCBot`, …); re-check robots.txt if you see access problems. The
search endpoint is public and unauthenticated by design. Even so: **keep volume low, use it
only for your own job search, never commercially, for bulk collection, or to build a
training corpus.**

## Commands

### Search job listings

```bash
bun run .agents/skills/getonboard-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — full-text keyword search. English and Spanish terms
  both work ("data analyst", "analista").
- `--location <text>` / `-l <text>` — **country only**: `Peru`/`PE`, `Chile`, `Colombia`,
  `Mexico`, `Argentina`, `Ecuador`, `Costa Rica`, `Spain` (name with or without accents, or
  the 2-letter code). The API has no city filter. An unrecognized value is a clean
  `BAD_LOCATION` error.
- `--jobage <days>` — published within N days (exact timestamps).
- `--page <n>` — server-side pagination (50/page). `--limit <n>` / `-n <n>` — client-side cap.
- `--format json|table|plain` — default `json`.

### Fetch full job detail

```bash
bun run .agents/skills/getonboard-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the composite `<company-slug>/<job-slug>` from a `search` result (e.g.
`talana-linq/analista-de-facturacion-talana-lima`), resolved through the API's `companies=`
filter. A bare job slug or getonbrd.com URL also works, via a best-effort search on the
slug's words; prefer ids from `search` output. Closed postings return `NOT_FOUND`.

## Usage examples

```bash
# Data analyst roles in Peru (local + remote-open-to-Peru), last 2 weeks
bun run .agents/skills/getonboard-search/cli/src/cli.ts search -q "data analyst" -l Peru --jobage 14 --format table

# Spanish-titled analyst roles in Peru
bun run .agents/skills/getonboard-search/cli/src/cli.ts search -q "analista" -l PE --format table

# Everything currently open for Peru
bun run .agents/skills/getonboard-search/cli/src/cli.ts search -l Peru --format table

# Full detail for one posting
bun run .agents/skills/getonboard-search/cli/src/cli.ts detail talana-linq/analista-de-facturacion-talana-lima --format plain
```

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Default — programmatic use, passing IDs to `detail` |
| `table` | Quick human-readable scanning |
| `plain` | Reading a single job's full detail (`detail` command) |

All errors are written to **stderr** as `{ "error": "...", "code": "..." }` and the process
exits with code `1`. Unknown flags are rejected (`UNKNOWN_FLAG`), never silently ignored.

## Notes

- Volume for Peru is modest (dozens to low hundreds of open roles at a time), and skewed to
  tech, data, product, and startup operations. Many postings publish a USD or CLP salary
  range; `detail` shows it when present.
- `--remote` is not offered: the API makes `remote` and `country_code` mutually exclusive,
  and `-l Peru` already includes remote roles open to Peru.
- GetOnBoard may rate-limit; the CLI retries 429/5xx with exponential backoff.

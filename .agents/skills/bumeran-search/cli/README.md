# bumeran-cli

CLI for searching jobs on **Bumeran Perú** (bumeran.com.pe), one of Peru's two biggest
general job boards (Navent/Jobint group).

**Data source**: Bumeran's own backend JSON API (`POST /api/avisos/searchV2`,
`GET /api/candidates/fichaAvisoNormalizada/<id>`), called directly; the site is a fully
client-rendered SPA with no server-rendered HTML to parse. See `../url-reference.md`.
**Authentication**: None. Requires the `x-site-id: BMPE` header; no cookies, no browser
impersonation (the Peru API answers an honest tool-naming User-Agent).
**Dependencies**: None (plain `bun` + `fetch`). `bun install` is optional and only pulls dev type defs.

> **Personal use only.** This reads an undocumented internal API. Keep volume low, don't use
> it commercially or for bulk data collection, and run it on your own responsibility. See
> `../SKILL.md`.

## Installation

```bash
cd .agents/skills/bumeran-search/cli
bun install   # optional — only installs TypeScript dev types
```

## Commands

| Command | Description |
|---------|-------------|
| `search` | Search for job listings, with server-side filters |
| `detail` | Fetch full detail for a single job listing |

`search` accepts `--format json|table|plain` (default `json`); `detail` accepts `--format json|plain`.
All errors are written to **stderr** as `{ "error": "...", "code": "..." }` with exit code `1`.

## Quick examples

```bash
bun run src/cli.ts search -q "analista de datos" -l "Lima" --jobage 7 --format table
bun run src/cli.ts search -q "practicante" -l "San Isidro" --format table
bun run src/cli.ts search --level trainee-pasante --jobage 1 --format table
bun run src/cli.ts search -q "analista financiero" --remote hybrid --level junior --sort recent --format table
bun run src/cli.ts detail 1118483020 --format plain
```

## Search flags

| Flag | Alias | Description |
|------|-------|--------------|
| `--query` | `-q` | Keywords (title-weighted; multi-word works). Optional. |
| `--location` | `-l` | Region (`"Lima"`, `"Cusco"`), Lima district (`"San Isidro"`, `"SJL"`, `"Callao"`), or `"<Region> en <City>"`. Server-side. |
| `--remote` | | `remote` \| `hybrid` \| `onsite`. Server-side. |
| `--level` | | `sin-experiencia` \| `trainee-pasante` \| `junior` \| `semi-sr` \| `senior` \| `senior-semi-senior` \| `jefe-supervisor-responsable` \| `otro`. Server-side. |
| `--jobage` | | Posted within N days (server bucket + exact client-side trim). |
| `--sort` | | `relevant` (default) \| `recent`. |
| `--page` | | 1-indexed page (20 results/page). |
| `--limit` | `-n` | Cap results emitted (client-side). |
| `--format` | | `json` \| `table` \| `plain`. |

## Tests

```bash
bun test --timeout 30000
```

Parsing, filter-mapping, and request-shape tests run offline against mocked responses; the
flag-validation tests spawn the CLI but exit before any network call.

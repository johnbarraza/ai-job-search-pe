---
name: bumeran-search
version: 1.0.0
description: >
  Use this skill to search live job listings on Bumeran Perú (bumeran.com.pe), one of
  Peru's two biggest general job boards and the one large and mid-size companies use most
  for white-collar and entry-level roles (analistas, practicantes, asistentes, ejecutivos).
  Supports server-side filters for region, Lima district, work mode, posting age, and
  seniority. Invoke for openings, internships, and hiring in Peru, or to look up a
  specific Bumeran posting. Trigger phrases include: Bumeran, empleos Perú, trabajo en
  Lima, ofertas de empleo, ofertas laborales, convocatorias, vacantes, prácticas,
  practicante, trainee, analista junior, trabajo remoto Perú, trabajo híbrido Lima, jobs
  Peru, jobs Lima, internships Peru, find a job, job search, job openings, hiring.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/bumeran-search/cli/src/cli.ts *)
---

# Bumeran Perú Search Skill

Search live job listings on **Bumeran Perú** (bumeran.com.pe). The site is a client-only
React app, so this CLI calls the same JSON API the site itself uses (`/api/avisos/searchV2`
for search, `/api/candidates/fichaAvisoNormalizada/<id>` for detail). No login, no API
key, **zero runtime dependencies**: it runs with just `bun`. Postings are in Spanish.

> Market-specific skill for Peru, adapted from the Bumeran Argentina skill in the
> [GabrielMensi/ai-job-search](https://github.com/GabrielMensi/ai-job-search) fork (same
> Navent/Jobint backend). Differences on the Peru site, verified live in October 2026:
> `x-site-id: BMPE`; the API answers an honest tool-naming User-Agent with **no** cookie
> warm-up (the Argentine site needed one); multi-word queries work; and the server-side
> facet filters work with the `{id, value: <idSemantico>}` shape (see `url-reference.md`).

## ⚠️ Personal use only

`robots.txt` disallows only a few HTML listing variants (`recientes=true`,
`relevantes=true`, `localidades=`, deep pagination, `/empleos-busquedaext-`); none of them
are API paths, and `/api/` is not disallowed. No login wall. Even so, this reads an
undocumented internal API: **keep volume low, use it only for your own job search, never
commercially or for bulk collection, and run it on your own responsibility.**

## When to use this skill

- Search Peruvian openings by keyword, narrowed **server-side** by region, Lima district,
  work mode, posting age, or seniority (the filters apply to the whole result set, not
  just the first page)
- Find internships (`--level trainee-pasante`, or query `practicante`)
- Get the full description, seniority, area, and external apply link for one posting

## Commands

### Search job listings

```bash
bun run .agents/skills/bumeran-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords, matched mostly against titles. Multi-word
  works (`"analista de datos"`), but rare titles return little: Bumeran had **one**
  "economista" posting nationwide when tested, against hundreds of "analista" ones.
  Prefer generic title words plus filters.
- `--location <text>` / `-l <text>` — server-side:
  - region: `"Lima"`, `"Arequipa"`, `"La Libertad"`, `"Cusco"` (sent as Bumeran's `cuzco`), …
  - Lima district: `"San Isidro"`, `"Miraflores"`, `"Surco"`, `"La Molina"`, `"SJL"`,
    `"SMP"`, `"Callao"`, … Districts that Bumeran stores under several spellings
    (`ate`/`ate-vitarte`, `surco`/`santiago-de-surco`, `magdalena`/`magdalena-del-mar`, …)
    are sent together and OR'd by the API.
  - `"<Region> en <City>"` for anywhere else: `"Piura en Sullana"`.
  - An unrecognized location exits 1 with `LOCATION_NOT_FOUND` instead of an empty list.
- `--remote <mode>` — `remote`, `hybrid`, or `onsite` (server-side).
- `--level <level>` — `sin-experiencia`, `trainee-pasante`, `junior`, `semi-sr`, `senior`,
  `senior-semi-senior`, `jefe-supervisor-responsable`, `otro` (server-side).
- `--jobage <days>` — posted within N days: uses the API's age bucket (hoy, 2–7 días,
  15 días, 1 mes) and trims to the exact window on the posting's full date.
- `--sort relevant|recent` — default `relevant`.
- `--page <n>` — 1-indexed (20 results/page). `--limit <n>` / `-n <n>` — client-side cap.
- `--format json|table|plain` — default `json`. JSON `meta` includes `totalResults` and
  the `filtros` actually sent.

### Fetch full job detail

```bash
bun run .agents/skills/bumeran-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the numeric aviso ID from `search` results (e.g. `1118483020`); a full
bumeran.com.pe posting URL also works. Returns the HTML description as clean text,
seniority, employment type, work mode, area/sub-area, and `applyUrl` when the employer
redirects to its own ATS (`null` means apply on Bumeran itself).

## Usage examples

```bash
# Data analyst roles in Lima, last 7 days
bun run .agents/skills/bumeran-search/cli/src/cli.ts search -q "analista de datos" -l "Lima" --jobage 7 --format table

# Internships in San Isidro
bun run .agents/skills/bumeran-search/cli/src/cli.ts search -q "practicante" -l "San Isidro" --format table

# Trainee/intern-level postings published today, anywhere
bun run .agents/skills/bumeran-search/cli/src/cli.ts search --level trainee-pasante --jobage 1 --format table

# Junior finance roles, hybrid, newest first
bun run .agents/skills/bumeran-search/cli/src/cli.ts search -q "analista financiero" --remote hybrid --level junior --sort recent --format table

# Full detail for one posting
bun run .agents/skills/bumeran-search/cli/src/cli.ts detail 1118483020 --format plain
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

- Confidential employers show as `"Confidencial"`; that is passed through as-is.
- Search results carry a one-paragraph plain-text `detalle` server-side, but the CLI
  doesn't emit it; use `detail` for the formatted description.
- Callao postings are mostly filed under provincia Lima (`peru|lima|callao`,
  `peru|lima|ventanilla`, …), so `-l Callao` filters on those districts.
- Bumeran may rate-limit; the CLI retries 429/5xx with exponential backoff.

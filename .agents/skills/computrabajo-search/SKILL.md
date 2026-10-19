---
name: computrabajo-search
version: 1.0.0
description: >
  Use this skill whenever the user wants to search for jobs in Peru, or asks about the
  Peruvian job market generally (any sector, not just tech), even if they don't mention
  Computrabajo by name. Computrabajo Perú (pe.computrabajo.com) is the highest-volume
  general job board in Peru, covering every sector and level from prácticas to gerencia,
  across Lima and every region. Invoke for open positions, vacancies, internships, and
  hiring anywhere in Peru, or to look up a specific Computrabajo posting. Trigger phrases
  include: Computrabajo, empleos Perú, trabajo en Lima, bolsa de trabajo, ofertas de
  trabajo, ofertas de empleo, convocatorias, vacantes, prácticas pre profesionales,
  prácticas profesionales, practicante, analista junior, trabajo Arequipa, trabajo
  Trujillo, jobs Peru, jobs Lima, find a job, job search, search for jobs, job openings,
  internships Peru, hiring.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
allowed-tools: Bash(bun run .agents/skills/computrabajo-search/cli/src/cli.ts *)
---

# Computrabajo Perú Search Skill

Search live job listings from **Computrabajo Perú** (pe.computrabajo.com), the largest
general-purpose job board in Peru by volume: all sectors, all levels (prácticas,
asistentes, analistas, jefaturas), Lima and every region. No authentication, no API key,
and **zero runtime dependencies**: it runs with just `bun`. Postings are in Spanish.

> Market-specific skill for the Peruvian job market. Adapted from the Computrabajo
> Argentina skill in the [GabrielMensi/ai-job-search](https://github.com/GabrielMensi/ai-job-search)
> fork (same platform and markup), re-verified live against pe.computrabajo.com, switched to
> an honest tool-naming User-Agent, and extended with Lima/Callao district resolution and
> Peruvian contract/schedule vocabulary.

## Access notes

Computrabajo's `robots.txt` has no blanket disallow and no named-AI-crawler entries; only
specific filter query parameters under `/ofertas-de-trabajo/` are disallowed (`dis=`,
`sal=`, `by=`, `pubdate=`, `cont=` and several `em*=` variants). This CLI never sends any of
them: it uses clean path-based URLs plus `?p=<page>`, which is not restricted. No login wall
on search or detail pages. Even so: **keep volume low, use it only for your own job
search, never commercially or for bulk data collection, and run it on your own
responsibility.**

## When to use this skill

- Search for openings anywhere in Peru by keyword, role, or career ("analista de datos",
  "practicante economía", "contador", "ejecutivo de banca")
- Narrow to a region (departamento) or to a Lima/Callao district
- Filter remote or hybrid roles
- Get the full description, requirements, salary chip, and contract type of one posting

## Commands

### Search job listings

```bash
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search [flags]
```

Key flags:
- `--query <text>` / `-q <text>` — keywords, e.g. `"analista de datos"`, `"practicante
  economia"`. At least one of `--query`/`--location` is required.
- `--location <text>` / `-l <text>` — one of:
  - a **region** (departamento): `"Lima"`, `"Arequipa"`, `"La Libertad"`, `"Piura"`,
    `"Cusco"`, `"Callao"`, …
  - a **Lima or Callao district**: `"San Isidro"`, `"Miraflores"`, `"Santiago de Surco"`,
    `"La Molina"`, `"Ventanilla"`, … including the shorthands `SJL`, `SJM`, `SMP`, `VES`,
    `VMT`, `Magdalena`, `Cercado de Lima`. The CLI nests these as `lima-en-<district>` /
    `callao-en-<district>`, which is how Computrabajo's own URLs spell them.
  - `"<Region> en <City>"` for any other city, e.g. `"Piura en Sullana"`. A bare city that
    is not a Lima/Callao district (e.g. just `"Sullana"`) silently returns zero results,
    not an error; see `url-reference.md`.
- `--remote <mode>` — `remote` or `hybrid`. `onsite` is a no-op: the site has no
  on-site-only filter.
- `--jobage <days>` — keep postings at most N days old. **Best-effort, client-side**: the
  site shows relative dates ("Hace 2 días") and its real `pubdate=` filter is
  robots-disallowed, so the CLI never sends it.
- `--page <n>` — 1-indexed page (20 results/page).
- `--limit <n>` / `-n <n>` — cap results emitted (client-side).
- `--format json|table|plain` — default `json`.

Each search result carries `salary` (e.g. `"S/. 3.500,00 (Mensual)"`, or `null` when the
employer publishes none) and `workplaceType` (`"Remoto"`, `"Presencial y remoto"`, or
`null` for on-site), in addition to the standard `id`, `title`, `company`, `location`,
`date`, `url`.

### Fetch full job detail

```bash
bun run .agents/skills/computrabajo-search/cli/src/cli.ts detail <id|url> [--format json|plain]
```

`id` is the 32-character hex ID from `search` results (e.g.
`A1159FCAE890A3F861373E686DCF3405`); a full pe.computrabajo.com posting URL also works.
Returns the full description, requirements, skills, salary / contract / schedule /
workplace chips, dates, and the apply link.

Dates: a search card shows only the posting's **last renewal** (employers "actualizan" a
posting to push it back to the top), so `--jobage` filters by renewal, not publication. The
detail page's JSON-LD has the publication dates: `date` is `datePosted`, the start of the
current publication period (republishing resets it - in an October 2026 sample, 11 of 36
renewed postings shared one datePosted - so treat the age as a floor), `updated` the
renewal when later than that, and `validThrough` the portal's expiry (`datePosted` + 60
days, not an employer deadline).
Relative dates ("Hoy", "Hace 3 horas") count on the Lima calendar (UTC-5). The JSON-LD also gives
`industry` (the employer's sector) and `district` ("Lima" when the employer gave only the city). See
`10-peru-market.md` section 10 and `tools/pe_frescura.py`.

### Company reviews

```bash
bun run .agents/skills/computrabajo-search/cli/src/cli.ts company <slug|url> [--area <name>] [--format json|plain]
```

`slug` is the company path from a posting's `companyUrl` (e.g. `adecco`). Returns the
company-wide `rating` with its review count (`reviews`), star `distribution`, `subratings`,
`recommendPct`, review counts per `areas` and `locations`, and the `sample` of reviews listed
on the page (stars, position, current/former, place, month, text). `--area "recursos
humanos"` fetches that area's page (`/<slug>/evaluaciones-de-<area>`, a clean path); the
side-box rating stays company-wide there, so judge the area by `matching` and the `sample`.
Reviews come in the site's "Más relevantes" order, not newest first. Read every rating with
its count, area and dates (`10-peru-market.md` section 11). The CLI never uses the
location/category query filters, which robots.txt disallows under `/empresas/`.

## Usage examples

```bash
# Data analyst roles in Lima, posted in the last week
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "analista de datos" -l "Lima" --jobage 7 --format table

# Economics internships in San Isidro (district auto-resolved)
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "practicante economia" -l "San Isidro" --format table

# Banking roles, hybrid only
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -q "analista de riesgos" --remote hybrid --format table

# Everything currently listed in Arequipa
bun run .agents/skills/computrabajo-search/cli/src/cli.ts search -l "Arequipa" --format table

# Full detail for one posting
bun run .agents/skills/computrabajo-search/cli/src/cli.ts detail A1159FCAE890A3F861373E686DCF3405 --format plain
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

- Company is often `"Importante empresa del sector"` or a staffing agency (ManpowerGroup,
  Adecco, Randstad…) recruiting for a client. That is what the listing shows, so it is
  passed through as-is; the client is sometimes named in the description ("para nuestro
  cliente del sector bancario").
- Santiago de Surco appears under two slugs on the site (`santiago-de-surco` and `surco`),
  depending on how the employer typed it. Search both if Surco matters to you.
- Peruvian internship postings state the convenio type in the title or description
  ("practicante preprofesional" = still studying; "practicante profesional" = egresado).
  Many also state a cycle or graduation-date window ("desde 6to ciclo", "egreso 2027-II").
  See `10-peru-market.md` in the job-application-assistant skill.
- Computrabajo may rate-limit; the CLI retries 429/5xx with exponential backoff.

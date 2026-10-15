# Search Queries for Job Scraper (Perú)

<!-- SETUP: Customize these queries based on your skills, target roles, and location -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. This Peru fork ships, enabled:

| CLI | Board | Peru-specific usage |
|---|---|---|
| `computrabajo-search` | pe.computrabajo.com (highest volume, every sector) | `-l "Lima"` or a district (`-l "San Isidro"`, `-l "SJL"`); `--remote remote\|hybrid` |
| `bumeran-search` | bumeran.com.pe (large/medium companies, analysts, interns) | server-side `-l`, `--remote`, `--level trainee-pasante\|junior\|…`, `--jobage` |
| `getonboard-search` | getonbrd.com (data, analytics, tech, startups) | always `-l Peru` (includes remote roles open to Peru) |
| `linkedin-search` | LinkedIn public jobs (banking, consulting, multinationals) | always `-l "Lima, Peru"` (or `-l "Peru"`, `-l "Arequipa, Peru"`) |
| `freehire-search` | freehire.me aggregator (tech) | `--country PE` |
| `jev-search` (opt-in, **disabled by default**) | Talento Perú, Laborum, Empleos Perú, Prácticas.pe, a university bolsa, through a real browser (jev-browse) | `--site talentoperu -q "<terms>" -l "<departamento>"`; paid model calls, slow (minutes per run): use 1-2 searches per `/scrape`, not one per query |

Bumeran matches mostly on titles: prefer generic title words (`"analista"`, `"practicante"`) plus filters over rare titles (`"economista"` returned one posting nationwide when tested).

The `site:` query templates below are the **WebSearch fallback**: for boards without a CLI (Laborum, Indeed Perú, Prácticas.pe, Talento Perú, Empleos Perú), company career pages, or when a CLI fails.

**Language scope:** write every query category in every language listed in your CLAUDE.md Languages table (for Peru, typically Spanish, plus English for multinationals). A posting requiring a language you have *not* declared, as a job condition, is excluded before scoring; a posting requiring a *higher level* than you declared in a language you *do* work in is flagged for your own judgment, not excluded — see `04-job-evaluation.md`'s Language Gate, the single source of truth for this rule. Translate each category's keywords rather than machine-translating word-for-word (e.g. "Data Analyst" -> "Analista de Datos", "Intern" -> "Practicante") if you work in more than one language.

## Search Sites

Primary (CLI-covered):
- **pe.computrabajo.com** - largest general board in Peru (`computrabajo-search`)
- **bumeran.com.pe** - large and mid-size employers (`bumeran-search`)
- **linkedin.com/jobs** - filter `Lima, Peru` (`linkedin-search`)
- **getonbrd.com** - data, analytics, tech, startups (`getonboard-search`)

Secondary (WebSearch fallback / manual):
- **laborum.pe** - corporate and administrative roles
- **pe.indeed.com** - aggregator (robots.txt blocks automated search; use `site:` or email alerts)
- **practicas.pe** - internship calls, mostly public sector
- **Talento Perú (SERVIR)** - every public-sector job and internship (`app.servir.gob.pe/DifusionOfertasExterno`)
- **[YOUR_UNIVERSITY_JOB_BOARD]** - your university's job board (login required: set email alerts, paste postings into `/apply`)
- Direct Google searches with `site:` filters for known target companies' career pages

## Query Categories

Queries are grouped by priority. Write **each category in every language from your Languages table** (see Language scope above). Combine each query with your location terms (city, district, or region) where the site supports it.

**Organize by function, not job title.** The same underlying work carries different titles across companies (an "Analista de Datos" role at one employer may be posted as "Analista de Inteligencia Comercial" or "Analista de Planeamiento" at another). Name each priority category after the function it covers, and list several plausible job titles as query variants within that category rather than betting an entire priority tier on one exact title string.

### Priority 1: [YOUR_PRIMARY_ROLE_TYPE]

These match your strongest and most desired career direction.

```
computrabajo-search: -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "[YOUR_CITY]" --jobage 14
bumeran-search:      -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "[YOUR_CITY]" --jobage 14
linkedin-search:     -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "[YOUR_CITY], Peru" --jobage 14
site:laborum.pe "[YOUR_PRIMARY_JOB_TITLE_1]" [YOUR_CITY]
site:pe.indeed.com "[YOUR_PRIMARY_JOB_TITLE_2]" [YOUR_CITY]
site:linkedin.com/jobs "[YOUR_PRIMARY_JOB_TITLE_1]" Peru
```

### Priority 2: [YOUR_DOMAIN_EXPERTISE]

These match your domain expertise.

```
computrabajo-search: -q "[YOUR_DOMAIN_KEYWORD_1]" -l "[YOUR_CITY]"
bumeran-search:      -q "[YOUR_DOMAIN_KEYWORD_1]" -l "[YOUR_CITY]"
getonboard-search:   -q "[YOUR_DOMAIN_KEYWORD_2]" -l Peru
site:linkedin.com/jobs [YOUR_DOMAIN_KEYWORD_1] Lima Peru
```

### Priority 3: [YOUR_ADJACENT_ROLE_TYPE]

Adjacent roles you could pivot into.

```
computrabajo-search: -q "[YOUR_ADJACENT_TITLE_1]" -l "[YOUR_CITY]"
bumeran-search:      -q "[YOUR_ADJACENT_TITLE_2]" -l "[YOUR_CITY]" --level junior
```

### Priority 4: Sector público y prácticas

Public-sector jobs and internships are published on Talento Perú with a fixed, short window (at least 10 business days); see `10-peru-market.md` section 2. Remove this category if you do not want public-sector roles.

```
jev-search:          --site talentoperu -q "[YOUR_PRIMARY_JOB_TITLE_1]" -l "[YOUR_CITY]"   (only when enabled)
site:app.servir.gob.pe "[YOUR_PRIMARY_JOB_TITLE_1]"
site:practicas.pe [YOUR_DOMAIN_KEYWORD_1] [YOUR_CITY]
site:gob.pe convocatoria CAS "[YOUR_PRIMARY_JOB_TITLE_1]" 2026
bumeran-search:      -q "practicante" -l "[YOUR_CITY]" --level trainee-pasante --jobage 14
computrabajo-search: -q "practicante [YOUR_DOMAIN_KEYWORD_1]" -l "[YOUR_CITY]" --jobage 14
```

### Priority 5: Broader roles

Wider net.

```
computrabajo-search: -q "[YOUR_KEY_SKILL]" -l "[YOUR_CITY]"
bumeran-search:      -q "[YOUR_KEY_SKILL]" --remote remote
linkedin-search:     -q "[YOUR_KEY_SKILL]" -l "Peru" --remote remote
```

## Location Filter

Lima commutes are measured in time, not distance. List districts, not just "Lima" (see `10-peru-market.md` section 8). Define acceptable areas:
- [YOUR_DISTRICT] and neighbouring districts
- [ACCEPTABLE_AREA_1] (e.g. San Isidro, Miraflores, Surco, San Borja)
- [ACCEPTABLE_AREA_2]
- [BORDERLINE_AREA] (borderline - ~X min by transit or car at rush hour)
- [TOO_FAR_AREA] (too far)
- Remote / hybrid: [YOUR_REMOTE_PREFERENCE] (days on-site per week you accept)

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine. Peruvian postings commonly require "inglés intermedio/avanzado": compare it against your declared English level.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown". Public-sector convocatorias carry an explicit closing date ("Fecha Fin de Publicación"): always record it as the deadline.

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
- "/scrape prácticas" -> Priority 4 internship queries across Bumeran (`--level trainee-pasante`), Computrabajo ("practicante ..."), LinkedIn ("practicante" / "intern", `-l "Lima, Peru"`) and Prácticas.pe

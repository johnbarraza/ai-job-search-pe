---
name: jev-search
version: 1.0.0
description: >
  Use this skill to read Peruvian job boards that the other portal CLIs cannot reach with
  a plain fetch, by driving a real Chrome with jev-browse (TypeSafe's Jev model):
  Talento Perú / SERVIR (public-sector jobs and prácticas), Laborum, Empleos Perú (MTPE),
  Prácticas.pe, Indeed Perú, or any other board such as a university bolsa de trabajo via
  --url. Opt-in: it needs paid model API keys and is disabled by default. Trigger phrases:
  Talento Perú, SERVIR, convocatorias CAS, empleo en el Estado, prácticas en el Estado,
  Laborum, Empleos Perú, bolsa de trabajo de la universidad, read this job board with the
  browser, jev.
context: fork
enabled: false  # opt-in: every run makes paid model calls (see Setup). Set true to let /scrape use it.
allowed-tools: Bash(bun run .agents/skills/jev-search/cli/src/cli.ts *)
---

# jev-search Skill

Reads job boards that a plain HTTP fetch cannot: stateful JSF apps (Talento Perú has no
per-posting URLs and needs its search form submitted), client-rendered SPAs (Laborum,
Empleos Perú), and boards behind your own login (a university bolsa). It drives Chrome with
**[jev-browse](https://github.com/0x7067/jev-browse)** (MIT, TypeScript), a browser agent
built on the same TypeSafe Jev decision model as browser-use's
[jev-ultrafast](https://github.com/browser-use/jev-ultrafast): Jev picks one operation and one element per step from an indexed table of
the page, and a small text model types search terms and writes the final answer, which this
CLI asks for as JSON and maps to the standard portal contract.

## How jev-browse is included (and updated)

jev-browse is a **git submodule** at `vendor/jev-browse`, tracking its `main` branch. This
CLI runs its committed bundle (`vendor/jev-browse/bundled/cli.mjs`), so nothing is built or
`npm install`ed. To take upstream updates:

```bash
git submodule update --init vendor/jev-browse           # first checkout of this repo
git submodule update --remote vendor/jev-browse         # pull jev-browse's latest main
git -C vendor/jev-browse log --oneline -5               # review what changed
(cd .agents/skills/jev-search/cli && bun test)         # contract tests still pass?
git add vendor/jev-browse && git commit -m "chore: update jev-browse"
```

The submodule is pinned to a commit: an update only takes effect when you commit it, so
read what changed first (it is code that drives your browser). jev-ultrafast itself is not
vendored: it is Python, needs Browser Harness, and its agent navigates but does not write
an answer from the page, which is what extracting postings needs.

## Setup (paid, opt-in)

1. Node 22+ and Chrome on the machine.
2. Model keys, in the environment or in `.env` at the repo root (gitignored):
   - `OPENROUTER_API_KEY` (or `TYPESAFE_API_KEY` with `JEV_PROVIDER=typesafe`): Jev decisions
   - `TEXT_MODEL_API_KEY` (plus optional `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`): typed text and
     the final answer
   See `vendor/jev-browse/.env.example` for every variable. **Every run makes paid model
   calls**, roughly one per page action (default budget 40 actions).
3. Set `enabled: true` above if you want `/scrape` to include it.

Without the keys the CLI exits 1 with `MISSING_CREDENTIALS` before starting anything.

## ⚠️ What it will and will not do

- **robots.txt-gated.** Every start URL goes through `tools/robots_check.py` first (the same
  gate as `09-web-research.md`). A disallowed or unreadable policy ends the run with
  `ROBOTS_DISALLOWED` before Chrome starts. LinkedIn's search, for example, is refused: use
  `linkedin-search` for LinkedIn.
- **Never works around bot checks.** jev-browse always runs with `--stop-at-challenge`: a
  CAPTCHA or verification page ends the run as `VERIFICATION_REQUIRED`. Indeed Perú usually
  ends this way; fall back to WebSearch or email alerts for it.
- **Read-only.** The goal forbids clicking apply/postular, signing in, typing personal data,
  or submitting anything but the site's own search form.
- **Page text leaves your machine.** The visible page text goes to the model providers.
  Don't point it at pages showing personal data you would not share.
- **Logged-in boards** (e.g. a university bolsa): jev-browse uses its own Chrome profile
  (`~/.jev-browse/profile`). Sign in there once by hand (`--headed`); the agent itself never
  signs in.
- **Model output is not ground truth.** Results are the model's reading of the page. Verify
  a posting's key facts (deadline, requirements) on the page before applying; `/apply`
  fetches and checks the posting itself.

## Commands

```bash
bun run .agents/skills/jev-search/cli/src/cli.ts sites
bun run .agents/skills/jev-search/cli/src/cli.ts search --site <id> [-q <terms>] [-l <location>] [flags]
bun run .agents/skills/jev-search/cli/src/cli.ts detail <url> [--format json|plain] [flags]
```

Sites (`sites` prints them as JSON): `talentoperu`, `laborum`, `practicas`, `empleosperu`,
`indeed`, and `url` (any board; requires `--url`).

Flags: `--site/-s`, `--query/-q`, `--location/-l`, `--url` (start URL; overrides a site's own),
`--limit/-n` (default 15, max 30), `--max-steps` (jev action budget, default 40, max 80),
`--timeout` (seconds, default 300), `--headed` (show Chrome), `--format json|table|plain`.
Unknown flags are rejected (`UNKNOWN_FLAG`).

Each result has the standard `id`, `title`, `company`, `location`, `date`, `url`, plus
`modality` (`presencial` / `híbrido` / `remoto` / `null`), `salary`, `deadline`, `ref`
(convocatoria number) and `site`. Talento Perú postings have no stable URL: `url` is `null`
and `id` is `talentoperu:<convocatoria number>`.

## Usage examples

```bash
# Public-sector roles for economists in Lima (Talento Perú)
bun run .agents/skills/jev-search/cli/src/cli.ts search --site talentoperu -q "economista" -l "Lima" --format table

# Public-sector internships
bun run .agents/skills/jev-search/cli/src/cli.ts search --site talentoperu -q "practicante" --format table

# Laborum
bun run .agents/skills/jev-search/cli/src/cli.ts search --site laborum -q "analista financiero" -l "Lima" --format table

# Your university's job board (sign in once with --headed first)
bun run .agents/skills/jev-search/cli/src/cli.ts search --site url --url "https://<your-bolsa>/ofertas" -q "practicante" --headed
```

## Errors

stderr JSON `{ "error", "code" }`, exit 1: `JEV_NOT_INSTALLED` (run `git submodule update
--init vendor/jev-browse`), `NODE_MISSING`, `MISSING_CREDENTIALS`, `ROBOTS_DISALLOWED`,
`VERIFICATION_REQUIRED`, `BLOCKED` (step budget or no progress), `JEV_ERROR`,
`SEARCH_FAILED` / `DETAIL_FAILED` (e.g. the answer held no parseable JSON).

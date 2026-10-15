# jev-search reference

Unlike the other portal skills, jev-search does not parse a site's HTML or call its API.
It hands a start URL and a natural-language goal to jev-browse, which drives Chrome, and
parses the JSON answer the goal asks for. This file records the start URLs, the access
checks, and the jev-browse interface the CLI depends on, for whoever updates either side.

## jev-browse interface used (vendor/jev-browse, checked at commit 0c11df8, 2026-09-30)

```
node vendor/jev-browse/bundled/cli.mjs --url <url> --goal <goal> --max-steps <n> --stop-at-challenge [--headed]
```

- stdout: one JSON line, the `RunResult`: `status` (`done` | `blocked` | `error`), `answer`
  (present when the goal asked for information and the answer passed jev-browse's own
  review), `answer_note`, `final_url`, `steps`, `elapsed_ms`, `blocked_cause`,
  `challenge_reasons`, `error`, … Exit code 0 = done, 2 = blocked, 1 = error.
- stderr: JSONL step events (ignored by this CLI).
- Credentials: `JEV_PROVIDER`, `TYPESAFE_API_KEY` / `OPENROUTER_API_KEY`, `TEXT_MODEL_API_KEY`,
  `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, read from the environment, then `.env` in the
  jev-browse package root, then `.env` in the working directory (the CLI runs it from the
  repo root).
- Browser: launches Chrome with the persistent profile `~/.jev-browse/profile` (or attaches
  via `--cdp`); one run per profile at a time (lock under `~/.jev-browse/`).

If an update changes these flags or the `RunResult` fields, update `src/helpers.ts`
(`jevArgs`, `runJev`, `RunResult`) and the fake-runner tests in `tests/cli.test.ts`.

## Start URLs and robots.txt (checked 2026-10-15 with tools/robots_check.py)

| Site id | Start URL | robots.txt verdict |
|---|---|---|
| `talentoperu` | `https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/ofertas_laborales.xhtml` | allowed (no robots.txt published; host behind Incapsula) |
| `laborum` | `https://www.laborum.pe/` | allowed |
| `practicas` | `https://www.practicas.pe/?s={q}` | allowed |
| `empleosperu` | `https://www.empleosperu.gob.pe/portal-mtpe/` | allowed (no robots.txt published) |
| `indeed` | `https://pe.indeed.com/jobs?q={q}&l={l}` | allowed for `/jobs?q=`; the site usually shows a bot check, which ends the run |
| `url` | `--url` | checked per run |
| (LinkedIn search) | `https://www.linkedin.com/jobs/search?...` | **disallowed for Claude-User**: refused; use `linkedin-search` |

The gate runs on every invocation, so a site that later disallows automated access is
refused automatically.

## Talento Perú specifics

The listing is a JSF/PrimeFaces form (`frmLstOfertsLabo`, `javax.faces.ViewState`): search
and pagination are POSTs, and "¡Ver más!" opens a posting through a form submit, so no
posting has a stable URL. Each card shows: title, entity, `Ubicación`, `Número de
Convocatoria`, `Cantidad de Vacantes`, `Remuneración`, `Fecha Inicio de Publicación`,
`Fecha Fin de Publicación`. The CLI uses the convocatoria number as the posting id
(`talentoperu:<number>`) and asks for the end date as `deadline`.

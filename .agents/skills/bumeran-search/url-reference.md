# Bumeran Perú (bumeran.com.pe) URL Reference

Bumeran is a **fully client-rendered React SPA**: every page (home, search, detail) returns
the same ~63 KB HTML shell with an empty `<div id="root">`, so there is nothing to parse in
the HTML. This skill calls the backend JSON API the app itself uses, on the same origin.

The endpoints were found by the Bumeran Argentina skill in the
[GabrielMensi/ai-job-search](https://github.com/GabrielMensi/ai-job-search) fork (from the
app's published source map) and re-verified live against the Peru site in October 2026.
Peru-specific findings are marked **(PE)**. Update this file if the API changes.

## Base and required headers

```
https://www.bumeran.com.pe
```

| Header | Value | Notes |
|---|---|---|
| `x-site-id` | `BMPE` | Required. Without it the backend returns `400 "No se incluyo el header \"x-site-id\""`. The shared Navent backend also serves `BMAR`, `ZJAR`, `BMMX`, `BMCL`, … |
| `User-Agent` | `Mozilla/5.0 (compatible; bumeran-cli/1.0)` | **(PE)** An honest tool-naming UA gets `200` from both endpoints, with no cookies at all. The Argentine site sat behind Cloudflare Bot Management and needed a warm-up GET for `__cf_bm` cookies plus a browser UA; Peru did not when tested, so this CLI sends neither. If Peru starts returning `403`, do not add browser impersonation to the CLI: escalation goes through the robots.txt gate in `09-web-research.md`. |
| `Content-Type` | `application/json` | For the POST search. |
| `Origin` / `Referer` | `https://www.bumeran.com.pe` | Sent for parity with the app; not verified as required. |

## Search: `POST /api/avisos/searchV2`

```
POST /api/avisos/searchV2?pageSize=<n>&page=<0-indexed>&sort=<RELEVANTES|RECIENTES>
{ "filtros": [ { "id": "<facet type>", "value": "<idSemantico>" } ], "query": "<text>", "internacional": false }
```

Response: `{ number, size, total, content: [...], filters: [...], filtersApplied: [...] }`.

### Query **(PE)**

Multi-word queries work on Peru (`"analista de datos"` → 87 results; the Argentine
investigation saw two-word queries return 0). Matching leans heavily on titles: `"analista"`
→ 3,140 results, `"economista"` → 1.

### Facet filters **(PE)**

The response's `filters` array lists every facet with counts. Each facet entry has `id`
(numeric), `idSemantico` (slug), `name`, `quantity`. **The filtro shape that works is
`{ "id": <facet type>, "value": <idSemantico> }`**:

| Shape tried | Result |
|---|---|
| `{"type":"provincia","id":"298307"}` | `400 Bad Request` |
| `{"id":"provincia","value":"298307"}` (numeric id) | `200`, `total: 0`, `filtersApplied: []` (silently ignored the whole request) |
| `{"id":"provincia","value":"peru\|arequipa"}` | `200`, `total: 118` = the facet's own `quantity` ✅ |

Facet types and the values this CLI uses (all verified live):

| Facet `id` | Values (idSemantico) | CLI flag |
|---|---|---|
| `provincia` | `peru\|lima`, `peru\|arequipa`, `peru\|la-libertad`, `peru\|cuzco` (not `cusco`), `peru\|piura`, `peru\|gobierno-regional-del-callao`, … | `--location <region>` |
| `localidad` | `peru\|lima\|san-isidro`, `peru\|lima\|santiago-de-surco`, `peru\|piura\|sullana`, … | `--location <district>` / `"<Region> en <City>"` |
| `modalidad_trabajo` | `presencial`, `hibrido`, `remoto` | `--remote onsite\|hybrid\|remote` |
| `nivel_laboral` | `sin-experiencia`, `trainee-pasante`, `junior`, `semi-sr`, `senior`, `senior-semi-senior`, `jefe-supervisor-responsable`, `otro` | `--level` |
| `dias_fecha_publicacion` | `publicacion-hoy`, `publicacion-menor-a-{2..7}-dias`, `publicacion-menor-a-15-dias`, `publicacion-menor-a-1-mes` | `--jobage` (smallest covering bucket) |

Other facets seen but not exposed: `area`, `subarea`, `tipo_trabajo` (full-time, part-time,
por-horas), `tipo_contratacion` (indeterminado, temporal, autonomo, pasantia),
`segmentacion_collar`, `apto_discapacitado`, `postulacion_rapida`.

Semantics:
- Several values of the **same** facet are **OR'd**: `localidad surco` (425) +
  `localidad santiago-de-surco` (1,554) together → 1,979.
- **Different** facets are **AND'd**: `provincia lima` + `modalidad_trabajo hibrido` → 648.
- Every applied filter is echoed in `filtersApplied` with its `idSemantico`; a `localidad`
  also echoes its parent `provincia`. An **unknown value is not an error**: `peru|nowhere`
  returns `200`, `total: 0`, and is absent from `filtersApplied`. The CLI uses that echo to
  fail loudly (`LOCATION_NOT_FOUND` / `FILTER_NOT_APPLIED`) instead of reporting "no jobs".

### District slugs are messy **(PE)**

`localidad` slugs derive from employer-typed text, so one district can appear several ways.
From the live `localidad` facet under `provincia=peru|lima`: `ate` + `ate-vitarte`;
`santiago-de-surco` + `surco` + `dpto-401-santiago-de-surco` + `urb-higuereta-santiago-de-surco`;
`magdalena-del-mar` + `magdalena`; `san-martin-de-porres` + `san-martin-de-porres-lima`;
`san-luis` + `distrito-de-san-luis`; `cercado-de-lima` + `lima`; `lurigancho` +
`chosica-lurigancho` + `chosica`; `punta-hermosa` + `distrito-de-punta-hermosa`;
`cieneguilla` + `distrito-de-cieneguilla`; `san-miguel` + `urb-maranga-san-miguel`;
`santa-anita` + `santa-anima-lima`. `locationFiltros()` sends all known variants.

Callao: postings are mostly filed under provincia Lima (`peru|lima|callao` 675,
`peru|lima|ventanilla`, `peru|lima|la-perla`, …); provincia
`peru|gobierno-regional-del-callao` has a single catch-all localidad. `-l Callao` sends the
Lima-filed Callao districts.

### Result fields

`content[]` items: `id`, `titulo`, `empresa` (`"Confidencial"` when `confidencial: true`),
`localizacion` (`"San Isidro, Lima"`), `fechaPublicacion` (`DD-MM-YYYY`),
`fechaHoraPublicacion`, `modalidadTrabajo`, `tipoTrabajo`, `detalle` (one unformatted
paragraph), `cantidadVacantes`, `salarioObligatorio`, `aptoDiscapacitado`, `logoURL`, …
No salary figures are returned.

### Result URL

Search items have no `seoFriendlyUrl`; the CLI rebuilds it as
`/empleos/<slug(titulo)>-<slug(empresa)>-<id>.html`. **(PE)** For confidential postings the
real `seoFriendlyUrl` omits the company segment (`/empleos/analista-de-compras-1118483020.html`),
so the CLI omits it too. The SPA routes on the trailing `-<id>.html` either way.

## Detail: `GET /api/candidates/fichaAvisoNormalizada/<id>`

Returns `{ aviso, productoLookAndFeel, avisosSimilares }`. Used `aviso` fields: `titulo`,
`empresa.denominacion` (`null` for confidential postings), `localizacion.detalle`
(`"San Isidro, Lima, Peru"`), `fechaPublicacion`, `descripcion` (HTML), `tipoTrabajo.nombre`,
`modalidadTrabajo.nombre`, `nivelLaboral.nombre`, `area.nombre` / `subArea.nombre`,
`redireccionURL` (external ATS, else `null`), `seoFriendlyUrl`. A missing id returns `404`.

## Access checks

- `robots.txt` (`https://www.bumeran.com.pe/robots.txt`): `User-agent: *` with narrow
  disallows on HTML listing variants (`/*recientes=true`, `/*relevantes=true`,
  `/*?localidades=*`, `/empleos.html/111`, `/empleos-busquedaext-`, `/empleos/aptitus/*`).
  `/api/` is not disallowed. The API's `sort=RECIENTES` query value is not the HTML
  `recientes=true` flag the rules target.
- No login is required for search or detail.
- Undocumented internal API: personal, low-volume use only (see `SKILL.md`).

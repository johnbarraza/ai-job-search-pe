#!/usr/bin/env python3
"""Review page for a search: one self-contained HTML file that follows the workflow.

It reads only what the workflow already wrote, so the page never says more than the
evaluation did:

  1. Búsqueda    job_scraper/seen_jobs.json (every posting /scrape saw, per portal)
  2. Encaje      the same file's /rank fields (score, verdict, strengths, gaps)
  3. Frescura    `tools/pe_frescura.py --json` output (/rank rule 8), when given
  4. Reputación  company_research/<company>.json `ratings` (04-job-evaluation.md)
  5. Acción      derived: postular ya / postular y confirmar / confirmar antes / ...

Offline and dependency-free: inline CSS and JS, no CDN. Every value from the state
files is HTML-escaped, and only http(s) URLs become links. The "revisada" checkboxes
are a per-browser convenience (localStorage) and never write back to the state.

Usage:
    python tools/pe_revision.py
    python tools/pe_revision.py --frescura reports/frescura.json --out reports/revision.html
    python tools/pe_revision.py --today 2026-10-18 --titulo "César Barraza"
"""

import argparse
import base64
import html
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pe_frescura", ROOT / "tools" / "pe_frescura.py")
pe_frescura = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe_frescura)

SHORTLIST = ("Strong Fit", "Good Fit")
ACTIONS = [  # (key, label, css class) in priority order
    ("ya", "Postular ya", "go"),
    ("pronto", "Postular pronto", "go"),
    ("confirmar", "Postular y confirmar", "warn"),
    ("antes", "Confirmar antes", "stop"),
    ("tiempo", "Si hay tiempo", "muted"),
    ("descartar", "Descartar", "out"),
]
ACTION_ORDER = {key: i for i, (key, _, _) in enumerate(ACTIONS)}
SMALL_N = 30  # below this a rating is only referential (10-peru-market.md section 11)


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def link(url, text) -> str:
    if isinstance(url, str) and re.match(r"^https?://", url):
        return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text)}</a>'
    return esc(text)


URGENT_DAYS = 2  # a stated deadline this close makes a shortlisted posting "postular ya"


def deadline_info(entry: dict, today: date) -> dict:
    """The stated closing date (never the portal's expiry) as a label, a filter bucket and a sort key."""
    try:
        closes = date.fromisoformat(str(entry.get("deadline")))
    except ValueError:
        return {"days": None, "label": "—", "bucket": "sin", "css": "", "sort": 99999}
    days = (closes - today).days
    when = closes.strftime("%d/%m")
    if days < 0:
        return {"days": days, "label": f"venció el {when}", "bucket": "vencida", "css": "past", "sort": 99998}
    if days == 0:
        label, bucket, css = "HOY", "hoy", "today"
    elif days == 1:
        label, bucket, css = f"mañana · {when}", "3d", "soon"
    elif days <= 3:
        label, bucket, css = f"en {days} días · {when}", "3d", "soon"
    elif days <= 7:
        label, bucket, css = f"en {days} días · {when}", "7d", "week"
    else:
        label, bucket, css = when, "mas", ""
    return {"days": days, "label": label, "bucket": bucket, "css": css, "sort": days}


def action_for(entry: dict, fresh: dict | None, today: date | None = None) -> str:
    """The next step for a posting, from its /rank verdict, its freshness risk and a close deadline."""
    if entry.get("location_verdict") == "FAIL" or entry.get("language_gate") == "FAIL":
        return "descartar"
    verdict = entry.get("rank_verdict")
    if verdict in SHORTLIST:
        days = deadline_info(entry, today).get("days") if today else None
        if days is not None and 0 <= days <= URGENT_DAYS:
            return "ya"  # a stated deadline is a live process: no time to confirm first
        risk = (fresh or {}).get("risk")
        if risk == "alto":
            return "antes"
        if risk == "medio":
            return "confirmar"
        return "ya" if (fresh or {}).get("window") == "fresca" else "pronto"
    if verdict == "Moderate Fit":
        return "tiempo"
    return "descartar"


def company_file(name: str) -> str:
    """04-job-evaluation.md's cache filename rule: lowercase, trim, spaces to hyphens."""
    return (name or "").strip().lower().replace(" ", "-") + ".json"


def load_logos(research_dir: Path) -> dict:
    """tools/pe_logos.py's index: company key -> PNG file in research_dir/logos."""
    try:
        index = json.loads((research_dir / "logos" / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return index if isinstance(index, dict) else {}


def logo_uri(research_dir: Path, logos: dict, company: str) -> str | None:
    """The employer's logo as a data: URI, so the page stays one offline file."""
    entry = logos.get(re.sub(r"\s+", "-", (company or "").strip().lower()))
    file = entry.get("file") if isinstance(entry, dict) else None
    if not isinstance(file, str) or not re.fullmatch(r"[a-z0-9_-]+\.png", file):
        return None  # the index may be hand-edited: only plain PNG names in the logos folder
    try:
        data = (research_dir / "logos" / file).read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\x89PNG"):
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


# Words that name the position level, not the team: what is left of a title is the area.
LEVEL_WORDS = re.compile(
    r"\b(practicantes?|pr[aá]cticas?|pre[- ]?profesional(?:es)?|profesional(?:es)?|preprofesional(?:es)?|programa|"
    r"trainee|asistente|analista|auxiliar|jr|junior|senior|sr|intern(?:ship)?|associates?|summer|off-cycle|"
    r"subgerencia|gerencia|departamento|dpto|grupo funcional|[aá]rea|per[uú]|lima|h[ií]brido|presencial|remoto|\d{4})\b",
    re.I,
)
ANONYMOUS = re.compile(r"confidencial|importante empresa|empleador no divulgado", re.I)


def area_of(title: str) -> str:
    """The team a posting belongs to, from its title: "Practicante - Dpto. de Investigación
    Financiera" -> "Investigación Financiera". Empty when the title names only a level."""
    text = re.sub(r"\(.*?\)", " ", title or "")
    text = LEVEL_WORDS.sub(" ", text)
    text = re.sub(r"[-–/|·,:.]", " ", text)
    stop = ("de", "del", "en", "y", "la", "el", "para", "e")
    words = text.split()
    while words and words[0].lower() in stop:
        words.pop(0)
    words = words[:5]
    while words and words[-1].lower() in stop:
        words.pop()
    return " ".join(words)


LEGAL_SUFFIX = re.compile(r"\b(s\.?\s?a\.?\s?[ac]\.?|s\.?\s?a\.?|s\.?\s?r\.?\s?l\.?|e\.?\s?i\.?\s?r\.?\s?l\.?|ltd\.?|llc|inc\.?|sac|saa)(?=\s|$)", re.I)


def company_query(company: str) -> str:
    """The company as people search it: its acronym when the name carries one ("Banco Central de
    Reserva del Perú (BCRP)" -> "BCRP"), without legal suffixes ("Credicorp Ltd." -> "Credicorp")."""
    acronym = re.search(r"\(([A-ZÁÉÍÓÚÑ]{2,6})\)", company or "")
    if acronym:
        return acronym.group(1)
    name = re.sub(r"\(.*?\)", " ", company or "")
    name = LEGAL_SUFFIX.sub(" ", name)
    return " ".join(name.replace(",", " ").split())


def people_search(keywords: str) -> str:
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(keywords)


def contacts_html(r: dict) -> str:
    """Links to find the team's leads, the recruiters and the named contact on LinkedIn. They are
    searches the candidate opens with their own account: nothing here fetches a profile."""
    company = (r.get("company") or "").strip()
    if not company or ANONYMOUS.search(company):
        return ""
    area = area_of(r.get("title") or "")
    name = company_query(company) or company
    links = []
    li = (((r.get("context") or {}).get("links") or {}).get("linkedin")) or ""
    m = re.match(r"^https?://[a-z]{0,3}\.?linkedin\.com/company/([^/?#]+)", li)
    if m:
        base = f"https://www.linkedin.com/company/{m.group(1)}/people/"
        links.append(link(base + ("?keywords=" + quote_plus(area) if area else ""), "Equipo del área"))
    links.append(link(people_search(f"jefe {area} {name}" if area else f"gerente {name}"), "Jefes"))
    links.append(link(people_search(f"reclutamiento talento {name}"), "Reclutamiento"))
    contact = r.get("contact")
    if isinstance(contact, str) and contact.strip():
        links.append(link(people_search(f"{contact.strip()} {name}"), contact.strip()))
    google = f'site:linkedin.com/in "{name}" (jefe OR gerente OR head) {area}'.strip()
    links.append(link("https://www.google.com/search?q=" + quote_plus(google), "Google"))
    return '<div class="how"><b>Contactos:</b> ' + " · ".join(links) + "</div>"


def logo_html(r: dict) -> str:
    if r.get("logo"):
        return f'<img class="logo" src="{esc(r["logo"])}" alt="" width="28" height="28">'
    initials = "".join(w[0] for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]+", r.get("company") or "")[:2]).upper()
    return f'<span class="logo none" aria-hidden="true">{esc(initials or "?")}</span>'


def load_ratings(research_dir: Path, company: str) -> list[dict] | None:
    path = research_dir / company_file(company)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ratings = ((doc.get("sources") or {}).get("reviews") or {}).get("ratings")
    return ratings if isinstance(ratings, list) else []


def fmt_es(value) -> str:
    """4.26 -> '4,26'; 20188 -> '20.188' (Peruvian Spanish separators)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "?"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.2f}".replace(".", ",")
    return f"{int(value):,}".replace(",", ".")


def fmt_rating(value) -> str:
    """4.26 -> '4,26'; 3.9 -> '3,9'; 4 -> '4,0'."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "?"
    text = f"{float(value):.2f}".rstrip("0")
    return (text + "0" if text.endswith(".") else text).replace(".", ",")


def rating_html(ratings: list[dict] | None) -> str:
    if ratings is None:
        return '<span class="dim">sin investigar</span>'
    if not ratings:
        return '<span class="dim">sin calificación (no es mala señal)</span>'
    parts = []
    for r in ratings:
        n = r.get("n")
        small = not isinstance(n, int) or n < SMALL_N  # no count shown counts as small
        area = ""
        if r.get("area"):
            area_n = r.get("area_n")
            tag = " · referencial" if isinstance(area_n, int) and area_n < SMALL_N else ""
            area = f'<br><span class="dim">{esc(r["area"])}: {esc(fmt_es(area_n))} opiniones{tag}</span>'
        latest = f' · última {esc(r["latest"])}' if r.get("latest") else ""
        ref = ' <span class="tag">referencial</span>' if small else ""
        count = f"n={esc(fmt_es(n))}" if isinstance(n, int) else "sin n"
        note = f'<br><span class="dim">{esc(r["note"])}</span>' if r.get("note") else ""
        parts.append(
            f'{link(r.get("url"), r.get("source") or "fuente")} <b>{esc(fmt_rating(r.get("rating")))}</b>'
            f' <span class="dim">({count}{latest})</span>{ref}{area}{note}'
        )
    return "<br>".join(parts)


FRESH_CSS = {"muy alta": "f4", "alta": "f3", "media": "f2", "baja": "f1"}


def freshness_of(fresh: dict | None) -> str:
    """pe_frescura's freshness level; frescura.json files written before it existed lack it."""
    if not fresh:
        return "sin revisar"
    level = fresh.get("freshness")
    if level in pe_frescura.FRESHNESS_ORDER:
        return level
    age = fresh.get("age_days")
    if not isinstance(age, int):
        return "sin fecha"
    if fresh.get("risk") == "alto" and age <= pe_frescura.ACTIVE_DAYS:
        return "baja"  # closed or expired
    for limit, name in ((pe_frescura.VERY_FRESH_DAYS, "muy alta"), (pe_frescura.FRESH_DAYS, "alta"), (pe_frescura.ACTIVE_DAYS, "media")):
        if age <= limit:
            return name
    return "baja"


def fresh_html(fresh: dict | None) -> str:
    if not fresh:
        return '<span class="dim">sin revisar</span>'
    floor = "≥" if fresh.get("age_is_minimum") else ""
    age = f"{floor}{fresh['age_days']} d" if fresh.get("age_days") is not None else "?"
    signals = "".join(f"<li>{esc(s)}</li>" for s in fresh.get("signals") or [])
    level = freshness_of(fresh)
    risk = fresh.get("risk")
    return (
        f'<span class="fresh {FRESH_CSS.get(level, "")}">{esc(level)}</span> · {esc(age)}'
        f'<br><span class="dim">publicada {esc(fresh.get("original_date") or "?")}</span>'
        + (f'<br><span class="risk {esc(risk)}">riesgo de ghost job {esc(risk)}</span>' if risk in ("medio", "alto") else "")
        + (f'<ul class="signals">{signals}</ul>' if signals else "")
    )


def bullets(items) -> str:
    items = [i for i in (items or []) if i]
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>" if items else '<span class="dim">—</span>'


# How each source reads to a person, and confidence as filled dots (tools/pe_contexto.py).
SOURCE_TEXT = {
    "aviso": "lo dice el aviso", "aviso + portal": "aviso y portal coinciden", "portal": "dato del portal",
    "aviso (sede del cliente)": "sede del cliente, según el aviso", "web": "buscado en la web", "nombre": "deducido del nombre",
}
CONF_DOTS = {"alta": ("●●●", "confianza alta"), "media": ("●●○", "confianza media"), "baja": ("●○○", "confianza baja")}


def maps_url(query: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


def _evidence(source, confidence) -> str:
    """'dato del portal ●●○' with the full wording in the tooltip."""
    if not source:
        return ""
    dots, label = CONF_DOTS.get(confidence or "", ("", ""))
    text = SOURCE_TEXT.get(source, source)
    title = f"{text}; {label}" if label else text
    return (f'<span class="ev" title="{esc(title)}">{esc(text)}'
            + (f' <span class="dots conf-{esc(confidence)}" aria-label="{esc(label)}">{dots}</span>' if dots else "")
            + "</span>")


MODALITY_CLASS = {"presencial": "pres", "híbrido": "hib", "remoto": "rem"}


def meta_html(r: dict) -> str:
    """Work mode as a coloured pill (it decides commutes), then level and portal, quieter."""
    modality = r.get("modality") or "no declarado"
    parts = [f'<span class="pill mod-{MODALITY_CLASS.get(modality, "nd")}">{esc(modality.capitalize())}</span>']
    if r.get("level") and r["level"] != "no declarado":
        parts.append(f'<span class="pill lvl">{esc(r["level"])}</span>')
    if r.get("portal"):
        parts.append(f'<span class="src">{esc(r["portal"].replace("-search", ""))}</span>')
    return " ".join(parts)


def context_html(ctx: dict | None) -> str:
    """Workplace and employer sector as chips, each with where the data came from and how sure it is."""
    if not ctx:
        return ""
    lg, rb, links = ctx.get("lugar") or {}, ctx.get("rubro") or {}, ctx.get("links") or {}
    districts = lg.get("districts") or []

    chips = []
    if lg.get("remote"):
        chips.append('<span class="chip kind">Remoto</span>')
    chips += [f'<span class="chip place">{esc(d)}</span>' for d in districts]
    # The Lima zone is left to the zone filter: on each row it only repeated the district.
    if not chips:
        chips.append('<span class="chip muted">Lugar sin dato</span>')
    notes = []
    if lg.get("address"):
        notes.append(esc(lg["address"]))
    if lg.get("residence_required"):
        notes.append("Pide vivir en o cerca de " + esc(", ".join(lg["residence_required"])))
    note_html = "".join(f'<div class="ctx-note">{n}</div>' for n in notes)
    place = (f'<div class="ctx-row"><span class="ctx-k">Lugar</span><div class="ctx-v">{" ".join(chips)} '
             f'{_evidence(lg.get("source"), lg.get("confidence"))}{note_html}</div></div>')

    label = rb.get("label") or ""
    kinds = [k for k, on in (("Consultora", rb.get("staffing") and "consultor" not in label.lower()),
                             ("Recluta para un cliente", rb.get("for_client")), ("Empresa anónima", rb.get("anonymous"))) if on]
    sector_chips = ([f'<span class="chip sector">{esc(label)}</span>'] if label
                    else ['<span class="chip muted">Rubro sin identificar</span>'])
    sector_chips += [f'<span class="chip kind">{esc(k)}</span>' for k in kinds]
    sector = (f'<div class="ctx-row"><span class="ctx-k">Rubro</span><div class="ctx-v">{" ".join(sector_chips)} '
              f'{_evidence(rb.get("source"), rb.get("confidence"))}</div></div>')

    buttons = []
    # A map only for a real address: a district alone drops the pin in its center, not at the job.
    if not lg.get("remote") and lg.get("address"):
        query = lg["address"]
        if districts and districts[0].lower() not in query.lower():
            query += f", {districts[0]}"
        buttons.append(f'<a class="btn" href="{esc(maps_url(query + ", Lima, Perú"))}" target="_blank" '
                       f'rel="noopener noreferrer" title="{esc(lg["address"])}">Mapa</a>')
    for key, label in (("website", "Web"), ("linkedin", "LinkedIn"), ("computrabajo", "Computrabajo")):
        if isinstance(links.get(key), str) and re.match(r"^https?://", links[key]):  # the file may be hand-edited
            buttons.append(f'<a class="btn" href="{esc(links[key])}" target="_blank" rel="noopener noreferrer">{label}</a>')
    actions = (f'<div class="ctx-row"><span class="ctx-k"></span><div class="ctx-v ctx-btns">{"".join(buttons)}</div></div>'
               if buttons else "")
    return f'<div class="ctx">{place}{sector}{actions}</div>'


def fresh_from_state(entry: dict, today: date) -> dict | None:
    """Freshness from posted_date alone, for postings with no portal detail (pasted from a
    Facebook group or a university board): age only, no ghost-job signals."""
    try:
        posted = date.fromisoformat(str(entry.get("posted_date")))
    except ValueError:
        return None
    age = (today - posted).days
    if age < 0:
        return None
    window = "fresca" if age <= pe_frescura.FRESH_DAYS else "en curso" if age <= pe_frescura.ACTIVE_DAYS else "vieja"
    fresh = {"age_days": age, "original_date": posted.isoformat(), "age_is_minimum": False, "window": window,
             "risk": None, "signals": ["solo la fecha de publicación (sin detalle del portal)"]}
    fresh["freshness"] = freshness_of(fresh)
    return fresh


def collect(state: dict, fresh_rows: list[dict], research_dir: Path, context_rows: list[dict] | None = None,
            today: date | None = None) -> dict:
    today = today or date.today()
    seen = state.get("seen") or {}
    fresh_by_id = {pe_frescura.posting_id(r): r for r in fresh_rows}
    ctx_by_id = {pe_frescura.posting_id(r): r for r in (context_rows or [])}
    logos = load_logos(research_dir)
    ranked, unranked = [], []
    for key, e in seen.items():
        if not isinstance(e, dict):
            continue
        row = dict(e, key=key)
        if e.get("status") == "ranked":
            pid = pe_frescura.posting_id({"url": e.get("url")})
            fresh = (fresh_by_id.get(pid) if pid else None) or fresh_from_state(e, today)
            row["fresh"] = fresh
            row["context"] = ctx_by_id.get(pid)
            row["action"] = action_for(e, fresh, today)
            row["closes"] = deadline_info(e, today)
            row["ratings"] = load_ratings(research_dir, e.get("company") or "")
            row["logo"] = logo_uri(research_dir, logos, e.get("company") or "")
            ranked.append(row)
        elif e.get("status") in (None, "new") and e.get("fit") in ("high", "medium"):
            unranked.append(row)
    ranked.sort(key=lambda r: (ACTION_ORDER[r["action"]], -(r.get("rank_score") or 0)))
    unranked.sort(key=lambda r: r.get("posted_date") or "", reverse=True)
    shortlist = [r for r in ranked if r.get("rank_verdict") in SHORTLIST]
    return {
        "seen": seen,
        "ranked": ranked,
        "unranked": unranked,
        "shortlist": shortlist,
        "portals": Counter((e or {}).get("portal") or "?" for e in seen.values()),
        "verdicts": Counter(r.get("rank_verdict") for r in ranked),
        "freshness": Counter(freshness_of(r["fresh"]) for r in shortlist),
        "rated": sum(1 for r in shortlist if r["ratings"]),
        "actions": Counter(r["action"] for r in ranked),
    }


_DARK = """--bg:#11151b;--card:#1a2029;--ink:#e6eaf0;--dim:#9aa6b5;--line:#2c3440;
--accent:#9cc1ea;--go:#4ade80;--go-bg:#14321f;--warn:#fbbf24;--warn-bg:#3a2e10;--stop:#f87171;--stop-bg:#3b1717;
--muted-bg:#2a313c;--out:#9aa6b5;--chip-place:#1d3a5c;--chip-sector:#23303f;--mod-pres:#c7d6ea;--mod-pres-bg:#253246;--mod-hib:#c4b5fd;--mod-hib-bg:#2e2350;color-scheme:dark"""

# Light tokens on :root; dark ones under prefers-color-scheme (unless the host forces light)
# and again under data-theme="dark", so a host theme toggle wins both ways.
CSS = """
/* Layout: the five workflow steps as a strip, then one scannable table per decision. */
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2430;--dim:#5f6b7a;--line:#dfe3e8;--accent:#1f3550;
--go:#15803d;--go-bg:#dcfce7;--warn:#a16207;--warn-bg:#fef3c7;--stop:#b91c1c;--stop-bg:#fee2e2;
--muted-bg:#e5e7eb;--out:#6b7280;--chip-place:#dbe8f6;--chip-sector:#eef1f5;--mod-pres:#1f3550;--mod-pres-bg:#e3e9f1;--mod-hib:#6d28d9;--mod-hib-bg:#ede9fe}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){""" + _DARK + """}}
:root[data-theme="dark"]{""" + _DARK + """}
[hidden]{display:none!important}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header,main,footer{max-width:1600px;margin:0 auto;padding-block:16px;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1,h2{text-wrap:balance}.score,.step .big{font-variant-numeric:tabular-nums}
a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
h1{font-size:22px;margin:0 0 4px;color:var(--accent)}h2{font-size:17px;margin:28px 0 10px;color:var(--accent)}
.dim{color:var(--dim)}a{color:var(--accent)}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:14px}
.step{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.step .n{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.step .big{font-size:24px;font-weight:700}.step small{display:block;color:var(--dim)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.filters input,.filters select{padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-size:12px;color:var(--dim);font-weight:600;background:var(--bg)}
td ul{margin:0;padding-left:16px}td li{margin:0 0 2px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.badge.go{background:var(--go-bg);color:var(--go)}.badge.warn{background:var(--warn-bg);color:var(--warn)}
.badge.stop{background:var(--stop-bg);color:var(--stop)}.badge.muted{background:var(--muted-bg);color:var(--dim)}
.badge.out{background:var(--muted-bg);color:var(--out)}
.risk{font-size:11.5px}.risk.medio{color:var(--warn)}.risk.alto{color:var(--stop)}
.fresh{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.fresh.f4{background:var(--go);color:var(--card)}.fresh.f3{background:var(--go-bg);color:var(--go)}
.fresh.f2{background:var(--warn-bg);color:var(--warn)}.fresh.f1{background:var(--stop-bg);color:var(--stop)}
.who{display:flex;gap:9px;align-items:flex-start}
.logo{flex:none;width:28px;height:28px;border-radius:6px;object-fit:contain;background:#fff;border:1px solid var(--line)}
.logo.none{display:inline-flex;align-items:center;justify-content:center;background:var(--muted-bg);color:var(--dim);font-size:11px;font-weight:700}
.score{font-size:18px;font-weight:700}.tag{font-size:11px;border:1px solid var(--line);border-radius:4px;padding:0 4px;color:var(--dim)}
.signals{color:var(--dim);font-size:12px}tr.done{opacity:.55}
.ctx{margin-top:8px;padding-top:8px;border-top:1px dashed var(--line);font-size:12px;display:grid;gap:5px}
.ctx-row{display:grid;grid-template-columns:48px minmax(0,1fr);gap:6px;align-items:start}
.ctx-k{font-size:10.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;padding-top:3px}
.ctx-v{display:flex;flex-wrap:wrap;align-items:center;gap:4px;min-width:0}
.ctx-v .ev,.ctx-v .ctx-note{flex-basis:100%}
table td:nth-child(1){width:28px}table td:nth-child(2){width:120px}table td:nth-child(3){width:84px}
table td:nth-child(4){min-width:330px;width:27%}table td:nth-child(5){width:12%}table td:nth-child(6){width:8%}
table td:nth-child(7){width:13%}
.close{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.close.today{background:var(--stop);color:var(--card)}.close.soon{background:var(--stop-bg);color:var(--stop)}
.close.week{background:var(--warn-bg);color:var(--warn)}.close.past{color:var(--dim);text-decoration:line-through}
.how{margin-top:5px;font-size:12px;color:var(--dim)}.how b{color:var(--ink)}
.urgent{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0}
.urgent ol{margin:6px 0 0;padding-left:20px}.urgent li{margin:5px 0}
.count{font-weight:600}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin-top:5px}
.pill{display:inline-block;padding:2px 10px;border-radius:6px;font-size:12px;font-weight:600;line-height:1.5}
.pill.mod-pres{background:var(--mod-pres-bg);color:var(--mod-pres)}.pill.mod-hib{background:var(--mod-hib-bg);color:var(--mod-hib)}
.pill.mod-rem{background:var(--go-bg);color:var(--go)}.pill.mod-nd{border:1px dashed var(--line);color:var(--dim);font-weight:500}
.pill.lvl{background:var(--muted-bg);color:var(--ink);font-weight:500}.src{font-size:11px;color:var(--dim)}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;line-height:1.6;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.chip.place{background:var(--chip-place);border-color:transparent;font-weight:600}
.chip.zone{color:var(--dim)}
.chip.sector{background:var(--chip-sector);border-color:transparent}
.chip.kind{background:var(--warn-bg);color:var(--warn);border-color:transparent}
.chip.muted{color:var(--dim);border-style:dashed}
.ev{font-size:11px;color:var(--dim)}
.dots{letter-spacing:1px}.dots.conf-alta{color:var(--go)}.dots.conf-media{color:var(--warn)}.dots.conf-baja{color:var(--stop)}
.ctx-note{color:var(--dim);font-size:11px}
.ctx-btns{gap:6px}
.btn{display:inline-block;padding:2px 10px;border:1px solid var(--accent);border-radius:6px;font-size:12px;text-decoration:none;color:var(--accent)}
.btn:hover{background:var(--accent);color:var(--card)}
.btn:focus-visible,button.sort:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.sort{all:unset;cursor:pointer;font:inherit;color:inherit;display:inline-flex;align-items:center;gap:4px}
button.sort:hover{color:var(--accent)}
.arrow::after{content:"↕";opacity:.45;font-size:11px}
th[aria-sort="ascending"] .arrow::after{content:"▲";opacity:1}
th[aria-sort="descending"] .arrow::after{content:"▼";opacity:1}
.legend{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;font-size:12px;color:var(--dim);margin:6px 0 2px}
details{margin:12px 0}summary{cursor:pointer;font-weight:600;color:var(--accent)}
.wrap{overflow-x:auto;min-width:0}.wrap table{min-width:1180px}
@media (max-width:900px){.flow{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.flow{grid-template-columns:minmax(0,1fr)}}
"""

JS = """
(function(){
  var KEY='pe_revision_done';
  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
  function save(v){try{localStorage.setItem(KEY,JSON.stringify(v))}catch(e){}}
  var done=load();
  document.querySelectorAll('input.done').forEach(function(cb){
    var tr=cb.closest('tr');cb.checked=!!done[cb.dataset.key];tr.classList.toggle('done',cb.checked);
    cb.addEventListener('change',function(){done[cb.dataset.key]=cb.checked;save(done);tr.classList.toggle('done',cb.checked);count();apply();});
  });
  function count(){var c=document.getElementById('cnt');if(c)c.textContent=document.querySelectorAll('#main input.done:checked').length;}
  count();
  var q=document.getElementById('q'),fa=document.getElementById('fa'),fm=document.getElementById('fm'),fr=document.getElementById('fr'),fz=document.getElementById('fz'),fc=document.getElementById('fc'),fd=document.getElementById('fd');
  var WITHIN={hoy:['hoy'],'3d':['hoy','3d'],'7d':['hoy','3d','7d']};
  function closeOk(b){var v=fc.value;if(!v)return true;if(v==='fecha')return b!=='sin';if(v==='sin')return b==='sin';return (WITHIN[v]||[]).indexOf(b)>=0;}
  function doneOk(tr){var v=fd.value;if(!v)return true;var d=tr.classList.contains('done');return v==='done'?d:!d;}
  function apply(){
    var t=(q.value||'').toLowerCase();
    document.querySelectorAll('#main tbody tr').forEach(function(tr){
      var ok=(!t||tr.dataset.text.indexOf(t)>=0)&&(!fa.value||tr.dataset.action===fa.value)
        &&(!fm.value||tr.dataset.modality===fm.value)&&(!fr.value||tr.dataset.fresh===fr.value)
        &&(!fz.value||tr.dataset.zones.split('|').indexOf(fz.value)>=0)&&closeOk(tr.dataset.close)&&doneOk(tr);
      tr.hidden=!ok;
    });
  }
  [q,fa,fm,fr,fz,fc,fd].forEach(function(el){el.addEventListener('input',apply);el.addEventListener('change',apply);});
  // Sortable headers: first click sorts best first, the next one reverses.
  document.querySelectorAll('button.sort').forEach(function(btn){
    btn.addEventListener('click',function(){
      var th=btn.closest('th'),table=btn.closest('table'),tbody=table.tBodies[0],key=btn.dataset.sort;
      var cur=th.getAttribute('aria-sort');
      var dir=cur==='none'?(btn.dataset.first==='asc'?'ascending':'descending'):(cur==='ascending'?'descending':'ascending');
      table.querySelectorAll('thead th[aria-sort]').forEach(function(o){o.setAttribute('aria-sort','none');});
      th.setAttribute('aria-sort',dir);
      var rows=Array.prototype.slice.call(tbody.rows),sign=dir==='ascending'?1:-1;
      rows.sort(function(a,b){
        var x=a.getAttribute('data-s-'+key),y=b.getAttribute('data-s-'+key),nx=parseFloat(x),ny=parseFloat(y);
        var c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:String(x).localeCompare(String(y),'es');
        return c*sign;
      });
      rows.forEach(function(r){tbody.appendChild(r);});
    });
  });
})();
"""


def render(data: dict, today: date, title: str | None, artifact: bool = False) -> str:
    """The page. `artifact` drops the document wrapper (the claude.ai Artifact publisher adds
    its own <!doctype>/<head>/<body>) and declares the safe-area side gutter it relies on."""
    page_title = f"Ofertas de {title}" if title else "Revisión de ofertas"
    head = (
        f'<title>{esc(page_title)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n<style>{CSS}</style>\n'
        if artifact
        else '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{esc(page_title)}</title><style>{CSS}</style></head><body>\n"
    )
    tail = "" if artifact else "</body></html>\n"
    return head + _body(data, today, title) + tail


def _body(data: dict, today: date, title: str | None) -> str:
    labels = {k: (label, css) for k, label, css in ACTIONS}
    sl = data["shortlist"]
    ready = data["actions"]["ya"] + data["actions"]["pronto"]
    confirm = data["actions"]["confirmar"] + data["actions"]["antes"]
    portals = " · ".join(f"{esc(p.replace('-search', ''))} {n}" for p, n in data["portals"].most_common())
    verdicts = " · ".join(f"{esc(v)} {n}" for v, n in data["verdicts"].most_common())
    order = list(pe_frescura.FRESHNESS_ORDER) + ["sin revisar"]
    freshness = " · ".join(f"{esc(k)} {data['freshness'][k]}" for k in order if data["freshness"][k]) or "—"
    steps = [
        ("1 · Búsqueda", len(data["seen"]), f"vistas · {portals}", "/scrape"),
        ("2 · Encaje", len(data["ranked"]), f"evaluadas · {verdicts}", "/rank"),
        ("3 · Frescura", len(sl), f"en lista corta · frescura {freshness}", "pe_frescura.py"),
        ("4 · Reputación", data["rated"], f"de {len(sl)} con calificación", "company"),
        ("5 · Acción", ready, f"para postular · {confirm} por confirmar", "/apply"),
    ]
    flow = "".join(
        f'<div class="step"><div class="n">{esc(n)} <span class="tag">{esc(cmd)}</span></div>'
        f'<div class="big">{esc(big)}</div><small>{sub}</small></div>'
        for n, big, sub, cmd in steps
    )

    def row(r: dict) -> str:
        label, css = labels[r["action"]]
        fresh = r.get("fresh") or {}
        meta = meta_html(r)
        ctx = r.get("context") or {}
        lg, rb = ctx.get("lugar") or {}, ctx.get("rubro") or {}
        zones = "|".join((["Remoto"] if lg.get("remote") else []) + (lg.get("zones") or []))
        text = " ".join(str(x or "") for x in (r.get("title"), r.get("company"), r.get("modality"), r.get("level"),
                                                 " ".join(lg.get("districts") or []), rb.get("label"))).lower()
        ratings = r.get("ratings") or []
        rating = next((x.get("rating") for x in ratings if isinstance(x.get("rating"), (int, float))), None)
        age = fresh.get("age_days")
        closes = r.get("closes") or {"label": "—", "bucket": "sin", "css": "", "sort": 99999}
        how = f'<div class="how"><b>Postular:</b> {esc(r["how_to_apply"])}</div>' if r.get("how_to_apply") else ""
        how += contacts_html(r)
        # Sort keys, one per sortable column (see the header buttons and the JS below).
        sort_keys = {
            "accion": ACTION_ORDER[r["action"]], "encaje": r.get("rank_score") or 0,
            "puesto": f'{r.get("title") or ""} {r.get("company") or ""}'.lower(),
            "frescura": age if isinstance(age, int) else 99999, "reputacion": rating if rating is not None else -1,
            "cierre": closes["sort"],
        }
        sort_attrs = " ".join(f'data-s-{k}="{esc(v)}"' for k, v in sort_keys.items())
        return (
            f'<tr data-action="{esc(r["action"])}" data-modality="{esc(r.get("modality"))}" '
            f'data-fresh="{esc(freshness_of(r.get("fresh")))}" data-close="{esc(closes["bucket"])}" data-zones="{esc(zones)}" data-text="{esc(text)}" {sort_attrs}>'
            f'<td><input type="checkbox" class="done" data-key="{esc(r["key"])}" aria-label="Revisada"></td>'
            f'<td><span class="badge {css}">{esc(label)}</span></td>'
            f'<td><div class="score">{esc(r.get("rank_score"))}</div><span class="dim">{esc(r.get("rank_verdict"))}</span></td>'
            f'<td><div class="who">{logo_html(r)}<div><b>{link(r.get("url"), r.get("title"))}</b><br>{esc(r.get("company"))}</div></div>'
            f'<div class="meta">{meta}</div>{how}{context_html(r.get("context"))}</td>'
            f'<td>{fresh_html(r.get("fresh"))}</td>'
            f'<td><span class="close {esc(closes["css"])}">{esc(closes["label"])}</span></td>'
            f'<td>{rating_html(r.get("ratings"))}</td>'
            f'<td>{bullets(r.get("strengths"))}</td>'
            f'<td>{bullets(r.get("gaps"))}</td></tr>'
        )

    def th(label: str, key: str, first: str, hint: str) -> str:
        # first click sorts "best first": highest score/rating, freshest, most urgent action, A to Z
        return (f'<th aria-sort="none"><button type="button" class="sort" data-sort="{key}" data-first="{first}" '
                f'title="Ordenar: {esc(hint)}">{esc(label)}<span class="arrow" aria-hidden="true"></span></button></th>')

    head = (
        "<thead><tr><th>✓</th>"
        + th("Acción", "accion", "asc", "más urgente primero")
        + th("Encaje", "encaje", "desc", "mayor puntaje primero")
        + th("Puesto", "puesto", "asc", "de la A a la Z")
        + th("Frescura", "frescura", "asc", "más reciente primero")
        + th("Cierre", "cierre", "asc", "la que cierra antes primero")
        + th("Reputación", "reputacion", "desc", "mejor calificación primero")
        + "<th>Fortalezas</th><th>Brechas</th></tr></thead>"
    )
    main_rows = [r for r in data["ranked"] if r["action"] != "descartar"]
    out_rows = [r for r in data["ranked"] if r["action"] == "descartar"]
    modalities = sorted({r.get("modality") for r in main_rows if r.get("modality")})
    zone_set = sorted({z for r in main_rows for z in ((((r.get("context") or {}).get("lugar") or {}).get("zones")) or [])})
    if any((((r.get("context") or {}).get("lugar") or {}).get("remote")) for r in main_rows):
        zone_set.append("Remoto")
    zone_opts = "".join(f'<option value="{esc(z)}">{esc(z)}</option>' for z in zone_set)
    action_opts = "".join(f'<option value="{k}">{esc(lbl)}</option>' for k, lbl, _ in ACTIONS if k != "descartar")
    modality_opts = "".join(f'<option value="{esc(m)}">{esc(m)}</option>' for m in modalities)
    unranked = "".join(
        f'<li>{esc(r.get("posted_date") or "?")} · {link(r.get("url"), r.get("title"))} · {esc(r.get("company"))}'
        f' <span class="dim">({esc(r.get("modality"))} · {esc(r.get("level"))})</span></li>'
        for r in data["unranked"]
    )
    heading = f"Revisión de ofertas · {esc(title)}" if title else "Revisión de ofertas"
    soon = sorted((r for r in main_rows if r["closes"]["bucket"] in ("hoy", "3d", "7d")),
                  key=lambda r: (r["closes"]["sort"], -(r.get("rank_score") or 0)))
    urgent = ""
    if soon:
        items = "".join(
            f'<li><span class="close {esc(r["closes"]["css"])}">{esc(r["closes"]["label"])}</span> '
            f'<b>{esc(r.get("rank_score"))}</b> · {link(r.get("url"), r.get("title"))} · {esc(r.get("company"))}'
            + (f'<div class="how"><b>Postular:</b> {esc(r["how_to_apply"])}</div>' if r.get("how_to_apply") else "")
            + contacts_html(r)
            + "</li>"
            for r in soon
        )
        urgent = (f'<div class="urgent"><b>Cierran en los próximos 7 días ({len(soon)})</b> '
                  f'<span class="dim">· fecha que la oferta escribe, no el vencimiento del portal</span><ol>{items}</ol></div>')

    return f"""<header><h1>{heading}</h1>
<div class="dim">Generado el {esc(today.isoformat())} desde <code>seen_jobs.json</code>, la frescura y <code>company_research/</code>.
El encaje es un triaje de <code>/rank</code>; <code>/apply</code> vuelve a evaluar antes de postular.</div>
<div class="flow">{flow}</div></header>
<main>
<h2>Para decidir ({len(main_rows)})</h2>
{urgent}
<div class="dim">Revisadas: <span class="count" id="cnt">0</span> de {len(main_rows)} · marca ✓ en cada oferta que ya viste.</div>
<div class="filters"><input id="q" type="search" placeholder="Buscar puesto o empresa" aria-label="Buscar">
<select id="fa" aria-label="Acción"><option value="">Toda acción</option>{action_opts}</select>
<select id="fm" aria-label="Modalidad"><option value="">Toda modalidad</option>{modality_opts}</select>
<select id="fr" aria-label="Frescura"><option value="">Toda frescura</option><option value="muy alta">muy alta</option><option value="alta">alta</option><option value="media">media</option><option value="baja">baja</option></select>
<select id="fz" aria-label="Zona"><option value="">Toda zona</option>{zone_opts}</select>
<select id="fc" aria-label="Cierre"><option value="">Todo cierre</option><option value="hoy">Cierra hoy</option><option value="3d">Hasta 3 días</option><option value="7d">Esta semana</option><option value="fecha">Con fecha de cierre</option><option value="sin">Sin fecha</option></select>
<select id="fd" aria-label="Revisadas"><option value="">Revisadas y pendientes</option><option value="pend">Solo pendientes</option><option value="done">Solo revisadas</option></select></div>
<div class="legend"><span><span class="pill mod-pres">Presencial</span> <span class="pill mod-hib">Híbrido</span> <span class="pill mod-rem">Remoto</span> <span class="chip place">Distrito</span> <span class="chip sector">Rubro</span> <span class="chip kind">Tipo de empresa</span></span>
<span>Confianza del dato: <span class="dots conf-alta">●●●</span> alta · <span class="dots conf-media">●●○</span> media · <span class="dots conf-baja">●○○</span> baja</span>
<span>Haz clic en Acción, Encaje, Puesto, Frescura, Cierre o Reputación para ordenar.</span></div>
<div class="wrap"><table id="main">{head}<tbody>{"".join(row(r) for r in main_rows)}</tbody></table></div>
<details><summary>Descartadas o no elegibles ({len(out_rows)})</summary>
<div class="wrap"><table>{head}<tbody>{"".join(row(r) for r in out_rows)}</tbody></table></div></details>
<details><summary>Vistas y relevantes, sin evaluar ({len(data["unranked"])})</summary><ul>{unranked}</ul></details>
<p class="dim">Frescura: edad desde la publicación original; "≥" es un mínimo (Computrabajo reinicia la fecha al republicar);
el vencimiento del portal no es una fecha de cierre (<code>10-peru-market.md</code>, sección 10).
Reputación: cada calificación con su n, área y fecha; con menos de {SMALL_N} opiniones es referencial y una certificación pagada no es independiente (sección 11).</p>
</main>
<footer class="dim">Generado por Claude Code · ai-job-search-pe · {esc(today.isoformat())}</footer>
<script>{JS}</script>
"""


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state", type=Path, default=Path("job_scraper/seen_jobs.json"))
    ap.add_argument("--frescura", type=Path, default=Path("reports/frescura.json"),
                    help="tools/pe_frescura.py --json output (skipped when missing)")
    ap.add_argument("--research", type=Path, default=Path("company_research"))
    ap.add_argument("--contexto", type=Path, default=Path("reports/contexto.json"),
                    help="tools/pe_contexto.py --json output: workplace and sector (skipped when missing)")
    ap.add_argument("--out", type=Path, default=Path("reports/revision-ofertas.html"))
    ap.add_argument("--titulo", help="name shown in the heading, e.g. the candidate's")
    ap.add_argument("--artifact", action="store_true",
                    help="omit the document wrapper, for publishing as a claude.ai Artifact")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (for testing)")
    args = ap.parse_args(argv)

    try:
        state = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.state}: {exc}", file=sys.stderr)
        return 1
    fresh_rows = []
    if args.frescura.is_file():
        try:
            fresh_rows = json.loads(args.frescura.read_text(encoding="utf-8")).get("postings", [])
        except (OSError, ValueError, AttributeError) as exc:
            print(f"cannot read {args.frescura}: {exc}", file=sys.stderr)
            return 1
    context_rows = []
    if args.contexto.is_file():
        try:
            context_rows = json.loads(args.contexto.read_text(encoding="utf-8")).get("postings", [])
        except (OSError, ValueError, AttributeError) as exc:
            print(f"cannot read {args.contexto}: {exc}", file=sys.stderr)
            return 1
    data = collect(state, fresh_rows, args.research, context_rows, args.today)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(data, args.today, args.titulo, args.artifact), encoding="utf-8")
    a = data["actions"]
    print(f"{args.out}: {len(data['ranked'])} evaluadas · postular {a['ya'] + a['pronto']} · "
          f"confirmar {a['confirmar'] + a['antes']} · si hay tiempo {a['tiempo']} · descartar {a['descartar']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

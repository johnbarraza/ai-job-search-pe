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
import html
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

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


def action_for(entry: dict, fresh: dict | None) -> str:
    """The next step for a posting, from its /rank verdict and its freshness risk."""
    if entry.get("location_verdict") == "FAIL" or entry.get("language_gate") == "FAIL":
        return "descartar"
    verdict = entry.get("rank_verdict")
    if verdict in SHORTLIST:
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


def fresh_html(fresh: dict | None) -> str:
    if not fresh:
        return '<span class="dim">sin revisar</span>'
    floor = "≥" if fresh.get("age_is_minimum") else ""
    age = f"{floor}{fresh['age_days']} d" if fresh.get("age_days") is not None else "?"
    signals = "".join(f"<li>{esc(s)}</li>" for s in fresh.get("signals") or [])
    return (
        f'<span class="risk {esc(fresh.get("risk"))}">{esc(fresh.get("risk"))}</span> '
        f'{esc(fresh.get("window"))} · {esc(age)}'
        f'<br><span class="dim">publicada {esc(fresh.get("original_date") or "?")}</span>'
        + (f'<ul class="signals">{signals}</ul>' if signals else "")
    )


def bullets(items) -> str:
    items = [i for i in (items or []) if i]
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>" if items else '<span class="dim">—</span>'


def collect(state: dict, fresh_rows: list[dict], research_dir: Path) -> dict:
    seen = state.get("seen") or {}
    fresh_by_id = {pe_frescura.posting_id(r): r for r in fresh_rows}
    ranked, unranked = [], []
    for key, e in seen.items():
        if not isinstance(e, dict):
            continue
        row = dict(e, key=key)
        if e.get("status") == "ranked":
            fresh = fresh_by_id.get(pe_frescura.posting_id({"url": e.get("url")}))
            row["fresh"] = fresh
            row["action"] = action_for(e, fresh)
            row["ratings"] = load_ratings(research_dir, e.get("company") or "")
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
        "risks": Counter((r["fresh"] or {}).get("risk", "sin revisar") for r in shortlist),
        "rated": sum(1 for r in shortlist if r["ratings"]),
        "actions": Counter(r["action"] for r in ranked),
    }


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2430;--dim:#5f6b7a;--line:#dfe3e8;--accent:#1f3550;
--go:#15803d;--go-bg:#dcfce7;--warn:#a16207;--warn-bg:#fef3c7;--stop:#b91c1c;--stop-bg:#fee2e2;
--muted-bg:#e5e7eb;--out:#6b7280}
@media (prefers-color-scheme:dark){:root{--bg:#11151b;--card:#1a2029;--ink:#e6eaf0;--dim:#9aa6b5;--line:#2c3440;
--accent:#9cc1ea;--go:#4ade80;--go-bg:#14321f;--warn:#fbbf24;--warn-bg:#3a2e10;--stop:#f87171;--stop-bg:#3b1717;
--muted-bg:#2a313c;--out:#9aa6b5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header,main,footer{max-width:1280px;margin:0 auto;padding:16px}
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
.risk{font-weight:700;text-transform:uppercase;font-size:11px}.risk.bajo{color:var(--go)}.risk.medio{color:var(--warn)}.risk.alto{color:var(--stop)}
.score{font-size:18px;font-weight:700}.tag{font-size:11px;border:1px solid var(--line);border-radius:4px;padding:0 4px;color:var(--dim)}
.signals{color:var(--dim);font-size:12px}tr.done{opacity:.55}
details{margin:12px 0}summary{cursor:pointer;font-weight:600;color:var(--accent)}
.wrap{overflow-x:auto}
@media (max-width:900px){.flow{grid-template-columns:repeat(2,1fr)}}
"""

JS = """
(function(){
  var KEY='pe_revision_done';
  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
  function save(v){try{localStorage.setItem(KEY,JSON.stringify(v))}catch(e){}}
  var done=load();
  document.querySelectorAll('input.done').forEach(function(cb){
    var tr=cb.closest('tr');cb.checked=!!done[cb.dataset.key];tr.classList.toggle('done',cb.checked);
    cb.addEventListener('change',function(){done[cb.dataset.key]=cb.checked;save(done);tr.classList.toggle('done',cb.checked);});
  });
  var q=document.getElementById('q'),fa=document.getElementById('fa'),fm=document.getElementById('fm'),fr=document.getElementById('fr');
  function apply(){
    var t=(q.value||'').toLowerCase();
    document.querySelectorAll('#main tbody tr').forEach(function(tr){
      var ok=(!t||tr.dataset.text.indexOf(t)>=0)&&(!fa.value||tr.dataset.action===fa.value)
        &&(!fm.value||tr.dataset.modality===fm.value)&&(!fr.value||tr.dataset.risk===fr.value);
      tr.style.display=ok?'':'none';
    });
  }
  [q,fa,fm,fr].forEach(function(el){el.addEventListener('input',apply);el.addEventListener('change',apply);});
})();
"""


def render(data: dict, today: date, title: str | None) -> str:
    labels = {k: (label, css) for k, label, css in ACTIONS}
    sl = data["shortlist"]
    ready = data["actions"]["ya"] + data["actions"]["pronto"]
    confirm = data["actions"]["confirmar"] + data["actions"]["antes"]
    portals = " · ".join(f"{esc(p.replace('-search', ''))} {n}" for p, n in data["portals"].most_common())
    verdicts = " · ".join(f"{esc(v)} {n}" for v, n in data["verdicts"].most_common())
    risks = " · ".join(f"{esc(k)} {n}" for k, n in data["risks"].most_common()) or "—"
    steps = [
        ("1 · Búsqueda", len(data["seen"]), f"vistas · {portals}", "/scrape"),
        ("2 · Encaje", len(data["ranked"]), f"evaluadas · {verdicts}", "/rank"),
        ("3 · Frescura", len(sl), f"en lista corta · riesgo {risks}", "pe_frescura.py"),
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
        meta = " · ".join(x for x in (r.get("modality"), r.get("level"), (r.get("portal") or "").replace("-search", "")) if x)
        text = " ".join(str(x or "") for x in (r.get("title"), r.get("company"), r.get("modality"), r.get("level"))).lower()
        return (
            f'<tr data-action="{esc(r["action"])}" data-modality="{esc(r.get("modality"))}" '
            f'data-risk="{esc(fresh.get("risk", ""))}" data-text="{esc(text)}">'
            f'<td><input type="checkbox" class="done" data-key="{esc(r["key"])}" aria-label="Revisada"></td>'
            f'<td><span class="badge {css}">{esc(label)}</span></td>'
            f'<td><div class="score">{esc(r.get("rank_score"))}</div><span class="dim">{esc(r.get("rank_verdict"))}</span></td>'
            f'<td><b>{link(r.get("url"), r.get("title"))}</b><br>{esc(r.get("company"))}<br><span class="dim">{esc(meta)}</span></td>'
            f'<td>{fresh_html(r.get("fresh"))}</td>'
            f'<td>{rating_html(r.get("ratings"))}</td>'
            f'<td>{bullets(r.get("strengths"))}</td>'
            f'<td>{bullets(r.get("gaps"))}</td></tr>'
        )

    head = (
        "<thead><tr><th>✓</th><th>Acción</th><th>Encaje</th><th>Puesto</th><th>Frescura</th>"
        "<th>Reputación</th><th>Fortalezas</th><th>Brechas</th></tr></thead>"
    )
    main_rows = [r for r in data["ranked"] if r["action"] != "descartar"]
    out_rows = [r for r in data["ranked"] if r["action"] == "descartar"]
    modalities = sorted({r.get("modality") for r in main_rows if r.get("modality")})
    action_opts = "".join(f'<option value="{k}">{esc(lbl)}</option>' for k, lbl, _ in ACTIONS if k != "descartar")
    modality_opts = "".join(f'<option value="{esc(m)}">{esc(m)}</option>' for m in modalities)
    unranked = "".join(
        f'<li>{esc(r.get("posted_date") or "?")} · {link(r.get("url"), r.get("title"))} · {esc(r.get("company"))}'
        f' <span class="dim">({esc(r.get("modality"))} · {esc(r.get("level"))})</span></li>'
        for r in data["unranked"]
    )
    heading = f"Revisión de ofertas · {esc(title)}" if title else "Revisión de ofertas"

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión de ofertas</title><style>{CSS}</style></head><body>
<header><h1>{heading}</h1>
<div class="dim">Generado el {esc(today.isoformat())} desde <code>seen_jobs.json</code>, la frescura y <code>company_research/</code>.
El encaje es un triaje de <code>/rank</code>; <code>/apply</code> vuelve a evaluar antes de postular.</div>
<div class="flow">{flow}</div></header>
<main>
<h2>Para decidir ({len(main_rows)})</h2>
<div class="filters"><input id="q" type="search" placeholder="Buscar puesto o empresa" aria-label="Buscar">
<select id="fa" aria-label="Acción"><option value="">Toda acción</option>{action_opts}</select>
<select id="fm" aria-label="Modalidad"><option value="">Toda modalidad</option>{modality_opts}</select>
<select id="fr" aria-label="Riesgo"><option value="">Todo riesgo</option><option value="bajo">bajo</option><option value="medio">medio</option><option value="alto">alto</option></select></div>
<div class="wrap"><table id="main">{head}<tbody>{"".join(row(r) for r in main_rows)}</tbody></table></div>
<details><summary>Descartadas o no elegibles ({len(out_rows)})</summary>
<div class="wrap"><table>{head}<tbody>{"".join(row(r) for r in out_rows)}</tbody></table></div></details>
<details><summary>Vistas y relevantes, sin evaluar ({len(data["unranked"])})</summary><ul>{unranked}</ul></details>
<p class="dim">Frescura: edad desde la publicación original; "≥" es un mínimo (Computrabajo reinicia la fecha al republicar);
el vencimiento del portal no es una fecha de cierre (<code>10-peru-market.md</code>, sección 10).
Reputación: cada calificación con su n, área y fecha; con menos de {SMALL_N} opiniones es referencial y una certificación pagada no es independiente (sección 11).</p>
</main>
<footer class="dim">Generado por Claude Code · ai-job-search-pe · {esc(today.isoformat())}</footer>
<script>{JS}</script></body></html>
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
    ap.add_argument("--out", type=Path, default=Path("reports/revision-ofertas.html"))
    ap.add_argument("--titulo", help="name shown in the heading, e.g. the candidate's")
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
    data = collect(state, fresh_rows, args.research)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(data, args.today, args.titulo), encoding="utf-8")
    a = data["actions"]
    print(f"{args.out}: {len(data['ranked'])} evaluadas · postular {a['ya'] + a['pronto']} · "
          f"confirmar {a['confirmar'] + a['antes']} · si hay tiempo {a['tiempo']} · descartar {a['descartar']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

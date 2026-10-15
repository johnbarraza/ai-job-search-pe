#!/usr/bin/env python3
"""Peruvian extension programmes (PEU, cursos de extensión, programas de especialización)
with their application windows, sorted by how soon they close.

Reads data/peru/programas_extension.json, the verified registry. Offline: it never fetches
anything. A date is shown as fact only when the registry marks the call `abierta`; calls
marked `por_confirmar` are listed separately with the official URL to check, and any entry
verified more than STALE_DAYS ago is flagged for re-verification before you rely on it.

Usage:
    python tools/pe_programas.py                 # open calls, soonest deadline first
    python tools/pe_programas.py --all           # every programme, including closed ones
    python tools/pe_programas.py --career economía
    python tools/pe_programas.py --json
    python tools/pe_programas.py --today 2026-10-15
"""

import argparse
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "peru" / "programas_extension.json"
URGENT_DAYS = 7
STALE_DAYS = 21


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def parse(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def annotate(program: dict, today: date) -> dict:
    """The programme plus derived fields: effective status, days left, urgency, staleness."""
    p = dict(program)
    close = parse(p.get("inscription_close"))
    opened = parse(p.get("inscription_open"))
    status = p.get("status", "por_confirmar")
    if status == "abierta" and close and close < today:
        status = "cerrada"
    if status == "abierta" and opened and opened > today:
        status = "por_abrir"
    p["effective_status"] = status
    p["days_left"] = (close - today).days if close and close >= today else None
    p["urgent"] = p["days_left"] is not None and status == "abierta" and p["days_left"] <= URGENT_DAYS
    verified = parse(p.get("verified_on"))
    p["stale"] = verified is None or (today - verified).days > STALE_DAYS
    return p


def select(programs: list[dict], today: date, show_all: bool, career: str | None) -> list[dict]:
    rows = [annotate(p, today) for p in programs]
    if career:
        needle = fold(career)
        rows = [r for r in rows if any(needle in fold(c) for c in r.get("careers", []))]
    if not show_all:
        rows = [r for r in rows if r["effective_status"] in ("abierta", "por_abrir", "por_confirmar")]
    order = {"abierta": 0, "por_abrir": 1, "por_confirmar": 2, "cerrada": 3}
    return sorted(rows, key=lambda r: (order.get(r["effective_status"], 9), r["days_left"] if r["days_left"] is not None else 10**6, r["institution"]))


def render(rows: list[dict], today: date) -> str:
    out = [f"Programas de extensión (Perú) al {today.isoformat()}"]
    groups = [
        ("abierta", "Abiertas"),
        ("por_abrir", "Por abrir"),
        ("por_confirmar", "Por confirmar: no presentes estas fechas como hechos; verifica en la URL oficial"),
        ("cerrada", "Cerradas"),
    ]
    for key, title in groups:
        group = [r for r in rows if r["effective_status"] == key]
        if not group:
            continue
        out.append(f"\n{title}")
        for r in group:
            when = r.get("inscription_close") or "fecha por confirmar"
            left = f" · {r['days_left']} días" if r["days_left"] is not None else ""
            flag = " 🔥" if r["urgent"] else ""
            stale = " · re-verificar" if r["stale"] else ""
            out.append(f"  {r['institution']:<12} cierra {when}{left}{flag} · {r.get('modality', 'no declarado')}{stale}")
            out.append(f"               {r['program']}")
            if r.get("eligibility"):
                 out.append(f"               Requisitos: {r['eligibility']}")
            if key == "por_confirmar" and r.get("notes"):
                 out.append(f"               Nota: {r['notes']}")
            out.append(f"               {r['url']}")
    return "\n".join(out)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--all", action="store_true", help="include closed programmes")
    ap.add_argument("--career", help="keep programmes whose careers mention this text (e.g. economía)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (for testing)")
    ap.add_argument("--data", type=Path, default=DATA, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    try:
        programs = json.loads(args.data.read_text(encoding="utf-8"))["programs"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"cannot read {args.data}: {exc}", file=sys.stderr)
        return 1
    rows = select(programs, args.today, args.all, args.career)
    if args.json:
        print(json.dumps({"today": args.today.isoformat(), "programs": rows}, ensure_ascii=False, indent=2))
    else:
        print(render(rows, args.today))
    return 0


if __name__ == "__main__":
    sys.exit(main())

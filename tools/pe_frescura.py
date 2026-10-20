#!/usr/bin/env python3
"""Freshness and ghost-job risk of job postings, from the portal CLIs' own output.

A posting's visible date is often not its age: Computrabajo shows the last renewal
("actualizada"), LinkedIn shows the repost date, and Bumeran republishes old avisos with a
new publication date. Most shortlists form in the first days, and a posting left up for
weeks may be a filled role nobody took down or a permanent candidate pool. This tool puts
the signals side by side and grades each posting:

  - age from the ORIGINAL publication date (`date` in each CLI's `detail` output);
  - renewal (`updated`), repost (`reposted`), portal expiry (`validThrough`), closed state
    (`isActive: false` or a Bumeran `status` other than "activo"), applicants;
  - for Bumeran and LinkedIn, whose ids are sequential, the creation date the id implies,
    calibrated on every (id, date) pair in the input - a far older id than its date says
    the aviso was republished.

Risk is a signal for the candidate, never a verdict on the employer: a renewed posting can
just as well mean the employer is still actively looking. Offline: it never fetches.

Usage:
    bun run .agents/skills/computrabajo-search/cli/src/cli.ts detail <id> > d1.json
    python tools/pe_frescura.py d1.json d2.json ... --calibrar search1.json job_scraper/seen_jobs.json
    python tools/pe_frescura.py job_scraper/seen_jobs.json --json
    python tools/pe_frescura.py d1.json --today 2026-10-18
"""

import argparse
import json
import re
import statistics
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

VERY_FRESH_DAYS = 3
FRESH_DAYS = 7  # the window in which most shortlists form
ACTIVE_DAYS = 21
OLD_DAYS = 45
REPOST_GAP_DAYS = 10  # id-implied creation this much earlier than the shown date = republished
MANY_APPLICANTS = 200
SEQUENTIAL_ID_PORTALS = ("bumeran", "linkedin")
RISK_ORDER = {"bajo": 0, "medio": 1, "alto": 2}
# Freshness reads the other way round from risk: "muy alta" is the newest posting.
FRESHNESS_ORDER = {"muy alta": 0, "alta": 1, "media": 2, "baja": 3, "sin fecha": 4}


def fold(text) -> str:
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").split())


def parse(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def portal_of(url: str) -> str:
    host = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    for name, domain in (("computrabajo", "computrabajo.com"), ("bumeran", "bumeran.com.pe"), ("linkedin", "linkedin.com")):
        if host == domain or host.endswith("." + domain):
            return name
    return "otro"


def numeric_id(posting: dict, portal: str) -> int | None:
    """The sequential id for Bumeran / LinkedIn postings, from the id field or the URL."""
    if portal not in SEQUENTIAL_ID_PORTALS:
        return None
    raw = str(posting.get("id") or "")
    if raw.isdigit():
        return int(raw)
    m = re.search(r"(\d{7,})(?:\.html)?/?(?:\?|$)", posting.get("url") or "")
    return int(m.group(1)) if m else None


def posting_id(posting: dict) -> str:
    """The portal's own id, from the id field or the URL, so a detail and a seen_jobs entry match."""
    if posting.get("id"):
        return str(posting["id"]).upper()
    url = posting.get("url") or ""
    m = re.search(r"([0-9A-Fa-f]{32}|\d{7,})(?:\.html)?/?(?:[?#]|$)", url)
    return m.group(1).upper() if m else url


def load_postings(path: Path) -> list[dict]:
    """Postings from a CLI detail object, a JSON array, a search output or seen_jobs.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("seen"), dict):
        return [
            {"title": e.get("title"), "company": e.get("company"), "url": e.get("url"), "date": e.get("posted_date")}
            for e in data["seen"].values()
            if isinstance(e, dict)
        ]
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return [p for p in data["results"] if isinstance(p, dict)]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    return []


class IdCalendar:
    """Maps a sequential posting id to the date it was most likely created, per portal.

    Fits day = a + k * id through the median id of each publication date with a
    Theil-Sen line (median of pairwise slopes): a republished aviso, or a whole day
    represented by one odd posting, cannot tilt it, so an outlier id stands out
    against its peers.
    """

    def __init__(self, postings: list[dict]):
        by_portal: dict[str, dict[date, list[int]]] = {}
        for p in postings:
            portal = portal_of(p.get("url") or "")
            pid, day = numeric_id(p, portal), parse(p.get("date"))
            if pid and day:
                by_portal.setdefault(portal, {}).setdefault(day, []).append(pid)
        self.lines: dict[str, tuple[float, float]] = {}
        for portal, days in by_portal.items():
            points = [(statistics.median(ids), day.toordinal()) for day, ids in days.items()]
            if len(points) < 3 or max(d for _, d in points) - min(d for _, d in points) < 5:
                continue
            slopes = [
                (d2 - d1) / (i2 - i1)
                for k, (i1, d1) in enumerate(points)
                for i2, d2 in points[k + 1 :]
                if i2 != i1
            ]
            if not slopes:
                continue
            per_id = statistics.median(slopes)
            if per_id <= 0:
                continue
            self.lines[portal] = (statistics.median(d - per_id * i for i, d in points), per_id)

    def created(self, portal: str, pid: int | None) -> date | None:
        line = self.lines.get(portal)
        if not line or pid is None:
            return None
        intercept, per_id = line
        return date.fromordinal(round(intercept + per_id * pid))


def annotate(posting: dict, today: date, calendar: IdCalendar, copies: int) -> dict:
    portal = portal_of(posting.get("url") or "")
    shown = parse(posting.get("date"))
    created = calendar.created(portal, numeric_id(posting, portal))
    republished = bool(shown and created and (shown - created).days >= REPOST_GAP_DAYS)
    original = min(shown, created) if republished else shown
    age = (today - original).days if original else None
    updated, expiry = parse(posting.get("updated")), parse(posting.get("validThrough"))
    applicants = posting.get("applicants")
    status = posting.get("status")
    closed = posting.get("isActive") is False or (status is not None and fold(status) != "activo")
    expired = bool(expiry and expiry < today)

    signals = []
    if closed:
        signals.append("cerrada en el portal")
    if expired:
        signals.append(f"vencida en el portal el {expiry.isoformat()}")
    elif expiry and (expiry - today).days <= 7:
        signals.append(f"el portal la retira el {expiry.isoformat()}")
    if updated:
        signals.append(f"renovada el {updated.isoformat()}")
    if posting.get("reposted"):
        signals.append("LinkedIn la marca como reposted")
    if republished:
        signals.append(f"id de ~{created.isoformat()}: aviso antiguo republicado (estimado)")
    if copies > 1:
        signals.append(f"misma empresa y título publicados {copies} veces")
    if isinstance(applicants, int) and applicants >= MANY_APPLICANTS:
        signals.append(f"{applicants}+ postulantes")
    elif isinstance(applicants, int):
        signals.append(f"{applicants} postulantes")
    elif posting.get("applicantsText"):
        signals.append(f"{posting['applicantsText']}")

    if closed or expired or (age is not None and age > OLD_DAYS):
        risk = "alto"
    elif (
        (age is not None and age > ACTIVE_DAYS)
        or posting.get("reposted")
        or republished
        or (isinstance(applicants, int) and applicants >= MANY_APPLICANTS)
    ):
        risk = "medio"
    else:
        risk = "bajo"

    if age is None:
        window = "sin fecha"
    elif age <= FRESH_DAYS:
        window = "fresca"
    elif age <= ACTIVE_DAYS:
        window = "en curso"
    elif age <= OLD_DAYS:
        window = "vieja"
    else:
        window = "muy vieja"

    # Freshness is the age alone (closed or expired postings are never fresh); the
    # ghost-job risk stays a separate signal, so a 3-day-old posting with 200+
    # applicants is still "muy alta" freshness at "medio" risk.
    if closed or expired:
        freshness = "baja"
    elif age is None:
        freshness = "sin fecha"
    elif age <= VERY_FRESH_DAYS:
        freshness = "muy alta"
    elif age <= FRESH_DAYS:
        freshness = "alta"
    elif age <= ACTIVE_DAYS:
        freshness = "media"
    else:
        freshness = "baja"

    if risk == "alto":
        advice = "no priorizar: probable plaza cubierta, pool permanente o aviso olvidado"
    elif risk == "medio":
        advice = "postula, pero confirma que sigue abierta (reclutador, correo o llamada)"
    elif window == "fresca":
        advice = "postula ya: los primeros días son los que más se revisan"
    else:
        advice = "postula pronto"

    return {
        "portal": portal,
        "id": posting.get("id"),
        "title": posting.get("title"),
        "company": posting.get("company"),
        "url": posting.get("url"),
        "shown_date": shown.isoformat() if shown else None,
        "original_date": original.isoformat() if original else None,
        "id_created_estimate": created.isoformat() if created else None,
        "age_days": age,
        # Computrabajo resets datePosted when a posting is republished: its age is a floor.
        "age_is_minimum": portal == "computrabajo",
        "updated": updated.isoformat() if updated else None,
        "valid_through": expiry.isoformat() if expiry else None,
        "applicants": applicants,
        "window": window,
        "freshness": freshness,
        "risk": risk,
        "signals": signals,
        "advice": advice,
    }


def evaluate(postings: list[dict], calibration: list[dict], today: date) -> list[dict]:
    calendar = IdCalendar(postings + calibration)
    ids_by_role: dict[tuple[str, str], set] = {}
    for p in postings + calibration:
        role = (fold(p.get("company")), fold(p.get("title")))
        ids_by_role.setdefault(role, set()).add(posting_id(p))
    rows = []
    for p in postings:
        role = (fold(p.get("company")), fold(p.get("title")))
        copies = len(ids_by_role[role]) if all(role) else 1
        rows.append(annotate(p, today, calendar, copies))
    return sorted(rows, key=lambda r: (RISK_ORDER[r["risk"]], r["age_days"] if r["age_days"] is not None else 10**6))


def render(rows: list[dict], today: date) -> str:
    out = [f"Frescura de ofertas al {today.isoformat()} (edad desde la publicación original)"]
    if any(r["age_is_minimum"] for r in rows):
        out.append("≥ = Computrabajo: inicio de la publicación vigente; la edad real puede ser mayor")
    for r in rows:
        floor = "≥" if r["age_is_minimum"] else ""
        age = f"{floor}{r['age_days']} d" if r["age_days"] is not None else "?"
        out.append(
            f"\n[frescura {r['freshness']:<9}] riesgo {r['risk']:<5} {age:>5} · publicada {r['original_date'] or '?'}"
            f" · {r['company'] or '—'} · {r['title'] or '—'}"
        )
        if r["signals"]:
            out.append("        " + "; ".join(r["signals"]))
        out.append(f"        → {r['advice']}")
        if r["url"]:
            out.append(f"        {r['url']}")
    return "\n".join(out)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path, help="CLI detail/search JSON, or seen_jobs.json")
    ap.add_argument("--calibrar", nargs="*", type=Path, default=[], help="extra JSON used only to date sequential ids")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (for testing)")
    args = ap.parse_args(argv)

    postings, calibration = [], []
    for target, paths in ((postings, args.files), (calibration, args.calibrar)):
        for path in paths:
            try:
                target.extend(load_postings(path))
            except (OSError, ValueError) as exc:
                print(f"cannot read {path}: {exc}", file=sys.stderr)
                return 1
    rows = evaluate(postings, calibration, args.today)
    if args.json:
        print(json.dumps({"today": args.today.isoformat(), "postings": rows}, ensure_ascii=False, indent=2))
    else:
        print(render(rows, args.today))
    return 0


if __name__ == "__main__":
    sys.exit(main())

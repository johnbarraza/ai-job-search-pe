#!/usr/bin/env python3
"""Find the same posting published on several portals, so it is reviewed and applied to once.

A company often posts one role on Bumeran, LinkedIn and Computrabajo, sometimes through an
intermediary ("Universia Perú" for Santander Consumer Bank), with a slightly different title.
The title alone misleads both ways: two roles of one company share words ("Practicante Pre
Profesional de ..."), and one role changes its title per portal. The description is the
evidence, but companies also open every posting with the same boilerplate. So two postings
are one when

  1. the smaller description's content words are almost all in the larger one
     (containment >= 0.9, at least 40 content words), and
  2. their roles agree: the title words left after dropping level words and company names
     ("Riesgos - Santander Consumer Bank" posted by Universia -> "riesgo consumer bank") are
     mostly shared, and neither is empty ("Associate, Peru" proves nothing). Program words stay,
     so a summer and an off-cycle program built on one template remain two postings.

The one with the higher fit score stays; the others get `duplicate_of: <key>` in
seen_jobs.json (with --write), and tools/pe_revision.py shows them as "También en ..." on the
one that stays. Offline: it reads the portal CLIs' saved `detail` output, never fetches.

Usage:
    python tools/pe_duplicados.py reports/detalles/*.json            # report only
    python tools/pe_duplicados.py reports/detalles/*.json --write    # record duplicate_of
"""

import argparse
import importlib.util
import itertools
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pe_revision", ROOT / "tools" / "pe_revision.py")
pe_revision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe_revision)
posting_id = pe_revision.pe_frescura.posting_id

CONTAINMENT = 0.9
MIN_WORDS = 40
STOP = set("""a al ante bajo con contra de del desde durante e el en entre la las le les lo los mas o para
por que se segun sin sobre su sus tu un una uno unos y ya the and of to in for with on at is are be our your
we you""".split())


def words(text) -> set[str]:
    folded = unicodedata.normalize("NFKD", (text or "").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]{3,}", folded) if w not in STOP}


def containment(a: set, b: set) -> float:
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return len(small & large) / len(small) if small else 0.0


# Level words say nothing about which role it is; program words (summer, off-cycle, a year) do,
# so unlike pe_revision.area_of they stay: a summer and an off-cycle program share a template.
LEVEL = re.compile(r"\b(practicantes?|practicas?|pre ?profesional(es)?|profesional(es)?|preprofesional(es)?|"
                   r"asistente|auxiliar|junior|jr|senior|sr|peru|lima|hibrido|presencial|remoto)\b")


def title_words(title: str, companies: tuple[str, ...]) -> set[str]:
    """The words that name the role: no level words, no company names (an intermediary often
    puts the client's name in the title: "Riesgos - Santander Consumer Bank")."""
    folded = unicodedata.normalize("NFKD", (title or "").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = LEVEL.sub(" ", re.sub(r"[^a-z0-9]+", " ", folded))
    names = set().union(*(words(c) for c in companies))
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words(folded) if w not in names}


PROGRAM = re.compile(r"^(intern|internship|summer|verano|off|cycle|trainee|programa|associate|analyst|\d{4})$")


def same_area(e1: dict, e2: dict) -> bool:
    companies = (e1.get("company") or "", e2.get("company") or "")
    a1, a2 = title_words(e1.get("title") or "", companies), title_words(e2.get("title") or "", companies)
    if not (a1 and a2) or containment(a1, a2) < 0.75:
        return False
    # One title naming a program the other lacks ("Associate" vs "Associates, Internship",
    # "Summer Analyst" vs "Off-Cycle Intern") is two programs, however alike the text.
    return not any(PROGRAM.match(w) for w in a1 ^ a2)


def load_details(paths) -> dict[str, dict]:
    out = {}
    for path in paths:
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("description"):
            out[posting_id(d)] = d
    return out


def find(seen: dict, details: dict) -> list[tuple[str, str, float]]:
    """(kept key, duplicate key, containment) for every duplicate pair."""
    rows = []
    for key, e in seen.items():
        if not isinstance(e, dict) or e.get("status") not in ("ranked", "new"):
            continue
        d = details.get(posting_id({"url": e.get("url")})) if e.get("url") else None
        if d:
            rows.append((key, e, words(d.get("description"))))
    pairs = []
    for (k1, e1, w1), (k2, e2, w2) in itertools.combinations(rows, 2):
        if min(len(w1), len(w2)) < MIN_WORDS or not same_area(e1, e2):
            continue
        c = containment(w1, w2)
        if c >= CONTAINMENT:
            s1, s2 = e1.get("rank_score") or 0, e2.get("rank_score") or 0
            keep, dup = (k1, k2) if (s1, len(w1)) >= (s2, len(w2)) else (k2, k1)
            pairs.append((keep, dup, c))
    # Chains (a ~ b ~ c) collapse onto the one that is kept.
    root = {}
    for keep, dup, _ in sorted(pairs, key=lambda p: -p[2]):
        while keep in root:
            keep = root[keep]
        if dup != keep and dup not in root:
            root[dup] = keep
    return [(root[d], d, c) for keep, d, c in pairs if d in root and root[d] != d]


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if getattr(stream, "reconfigure", None):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("details", nargs="+", help="portal CLI `detail` JSON files")
    ap.add_argument("--state", type=Path, default=Path("job_scraper/seen_jobs.json"))
    ap.add_argument("--write", action="store_true", help="record duplicate_of in the state file")
    args = ap.parse_args(argv)

    doc = json.loads(args.state.read_text(encoding="utf-8"))
    seen = doc.get("seen", {})
    found = {}
    for keep, dup, c in find(seen, load_details(args.details)):
        found[dup] = (keep, c)
    for dup, (keep, c) in sorted(found.items()):
        a, b = seen[keep], seen[dup]
        print(f"{b.get('company')} · {b.get('title')} ({b.get('portal')})\n"
              f"  = {a.get('company')} · {a.get('title')} ({a.get('portal')})  [descripción {c:.0%}]")
    if args.write:
        for key, e in seen.items():
            if isinstance(e, dict) and "duplicate_of" in e and key not in found:
                del e["duplicate_of"]  # a rerun on new evidence can undo an old match
        for dup, (keep, _) in found.items():
            seen[dup]["duplicate_of"] = keep
        args.state.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(found)} duplicadas" + (" (guardado en " + str(args.state) + ")" if args.write else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Look up a Peruvian company's crowdsourced salaries on MyWorkIn and merge them
into salary_data.json, so salary_lookup.py (and /apply's salary step) can use them.

MyWorkIn (https://www.myworkin.ai/salaries) publishes salary reports per company:
one row per role with an estimated monthly range in soles and the number of reports
("aportes"). The page states: "Montos estimados en soles mensuales. USD ≈ S/ 3.75;
anuales ÷ 12."

This is an on-demand, one-company-at-a-time tool for a personal job search, not a
mirror: each lookup costs one request for the company page, plus one for the
company index when the local cache (.cache/myworkin_index.json, 7 days) is stale.
Before any request it reads robots.txt and refuses paths it disallows (as of
2026-10-15, /salaries is allowed; /jobs and /api are not).

Usage:
    python tools/myworkin_salaries.py "Credicorp"
    python tools/myworkin_salaries.py "Rímac Seguros" --json
    python tools/myworkin_salaries.py "BCP" --no-save          # print only
    python tools/myworkin_salaries.py --refresh-index "Interbank"
    python tools/myworkin_salaries.py --slug ferreycorp         # skip name matching

Data caveats: reports are self-submitted and often a single person per role; treat
every figure as a rough indicator, never as the company's pay scale.
"""

import argparse
import html
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.myworkin.ai"
# Alphabetical, every company on one page (468 companies, 2026-10-15). Name order keeps the
# cached index stable between refreshes; the default order (by report count) reshuffles.
INDEX_URL = f"{BASE}/salaries?sort=name&perPage=999"
UA = "Mozilla/5.0 (compatible; myworkin-salary-tool/1.0; personal job search)"
CACHE_FILE = ROOT / ".cache" / "myworkin_index.json"
CACHE_TTL = timedelta(days=7)
DEFAULT_OUTPUT = ROOT / "salary_data.json"
SOURCE_NAME = "MyWorkIn (myworkin.ai/salaries)"
MIN_MATCH_SCORE = 70

# Acronyms Peruvians use for employers whose MyWorkIn name spells them out. The fuzzy
# matcher cannot get from "BCP" to "Banco de Crédito del Perú" on its own.
ACRONYMS = {
    "bcp": "banco-de-credito-del-peru",
    "bcrp": "banco-central-de-reserva-del-peru-bcrp",
}


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuse the repo's own company-name matcher and robots.txt parser rather than
# re-implementing either.
salary_lookup = _load_module("salary_lookup", ROOT / "salary_lookup.py")
robots_check = _load_module("robots_check", ROOT / "tools" / "robots_check.py")


class FetchError(RuntimeError):
    pass


def http_get(url, retries=4):
    """GET with an honest UA, a hard timeout, and backoff on 429/5xx."""
    delay = 1.0
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if (e.code == 429 or e.code >= 500) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise FetchError(f"HTTP {e.code} for {url}") from e
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise FetchError(f"could not reach {url}: {e.reason}") from e
    raise FetchError(f"giving up on {url}")


def check_robots(path):
    """Refuse to fetch a path MyWorkIn's robots.txt disallows."""
    text = http_get(f"{BASE}/robots.txt")
    if text is None:
        return  # no published policy
    if not robots_check.is_robots_body(text):
        raise FetchError("robots.txt did not parse; refusing to fetch without a readable policy")
    if not robots_check.allowed(text, "myworkin-salary-tool", path):
        raise FetchError(f"robots.txt disallows {path}; not fetching")


def _clean(fragment):
    text = re.sub(r"<!--.*?-->", "", fragment, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# The card's logo goes through Next's image proxy; the original lives in Firebase Storage.
LOGO = re.compile(r"/_next/image\?url=(https?%3A%2F%2Ffirebasestorage\.googleapis\.com[^&\"\s]+)")


def parse_index(page):
    """Company cards on /salaries: [{slug, name, sector, reports, logo}]."""
    companies = []
    seen = set()
    for m in re.finditer(r'<a[^>]*href="/salaries/([a-z0-9-]+)"[^>]*>(.*?)</a>', page, flags=re.S):
        slug, card = m.group(1), m.group(2)
        if slug in seen:
            continue
        name = re.search(r"<h3[^>]*>(.*?)</h3>", card, flags=re.S)
        if not name:
            continue
        seen.add(slug)
        sector = re.search(r"<p[^>]*text-muted-foreground[^>]*>(.*?)</p>", card, flags=re.S)
        reports = re.search(r">\s*(\d+)\s*(?:<!--\s*-->)?\s*salarios?\s*<", card)
        logo = LOGO.search(card)
        companies.append({
            "slug": slug,
            "name": _clean(name.group(1)),
            "sector": _clean(sector.group(1)) if sector else None,
            "reports": int(reports.group(1)) if reports else None,
            "logo": urllib.parse.unquote(html.unescape(logo.group(1))) if logo else None,
        })
    return companies


AMOUNT = r"S/\s*([\d.,]+)"


def _amount(text):
    return int(re.sub(r"[.,]", "", text))


def parse_company(page):
    """A company's /salaries/<slug> page: name, total reports, and role rows."""
    name = re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.S)
    total = re.search(r"(\d+)\s*(?:<!--\s*-->)?\s*reportes", page)
    table = re.search(r"<table.*?</table>", page, flags=re.S)
    roles = []
    if table:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), flags=re.S):
            cells = [_clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
            if len(cells) < 2:
                continue
            amounts = re.findall(AMOUNT, cells[1])
            if not amounts:
                continue
            low = _amount(amounts[0])
            high = _amount(amounts[-1])
            roles.append({
                "role": cells[0],
                "salary_text": cells[1].lstrip("~ ").strip(),
                "min": low,
                "max": high,
                "reports": int(cells[2]) if len(cells) > 2 and cells[2].isdigit() else None,
            })
    return {
        "name": _clean(name.group(1)) if name else None,
        "reports": int(total.group(1)) if total else None,
        "roles": roles,
    }


def load_index(refresh=False):
    if not refresh and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(cached["fetched"])
            if datetime.now() - fetched < CACHE_TTL and cached.get("companies"):
                return cached["companies"]
        except (ValueError, KeyError, TypeError):
            pass  # unreadable cache: refetch
    check_robots("/salaries")
    page = http_get(INDEX_URL)
    if page is None:
        raise FetchError("the MyWorkIn salaries index returned 404")
    companies = parse_index(page)
    if not companies:
        raise FetchError("no companies parsed from the MyWorkIn index; the page layout may have changed")
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"fetched": datetime.now().isoformat(timespec="seconds"), "companies": companies},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return companies


def best_matches(companies, query):
    scored = []
    for c in companies:
        score = max(salary_lookup.match_score(query, c["name"]),
                    salary_lookup.match_score(query, c["slug"].replace("-", " ")))
        if score >= MIN_MATCH_SCORE:
            scored.append((score, c))
    scored.sort(key=lambda x: (-x[0], -(x[1]["reports"] or 0)))
    return scored


def to_salary_entry(slug, parsed):
    """Shape a company for salary_lookup.py: one category per role, the range as a
    string index (salary_lookup prints string indexes verbatim) and reports as count."""
    categories = {}
    for r in parsed["roles"]:
        label = r["role"]
        n = 2
        while label in categories:  # identical role titles stay distinct rows
            label = f"{r['role']} ({n})"
            n += 1
        categories[label] = {"count": r["reports"], "index": f"S/ {r['min']:,} – {r['max']:,}"}
    return {
        "company": parsed["name"] or slug,
        "city": "Perú",
        "categories": categories,
        "source_url": f"{BASE}/salaries/{slug}",
        "fetched": date.today().isoformat(),
        "total_reports": parsed["reports"],
    }


METADATA = {
    "source": SOURCE_NAME,
    "index_baseline": 0,
    "index_label": "Rango S/",
    "baseline_description": (
        "MyWorkIn: rangos mensuales estimados en soles (brutos según reporte), autodeclarados; "
        "Count = número de aportes por puesto. Con 1-2 aportes, tómalo solo como referencia."
    ),
}


def merge(output, entry):
    """Insert or replace one company in a MyWorkIn-sourced salary_data.json.

    Refuses to write into a file built from another source (union statistics, an Excel
    export): mixing a soles range into an index-based dataset would mislabel both.
    """
    if output.exists():
        data = json.loads(output.read_text(encoding="utf-8"))
        source = (data.get("metadata") or {}).get("source")
        if source != SOURCE_NAME:
            raise SystemExit(
                f"{output.name} already holds data from another source ({source!r}); not mixing. "
                f"Pass --output <other.json> or --no-save."
            )
    else:
        data = {"metadata": METADATA, "companies": []}
    companies = [c for c in data.get("companies", []) if c.get("source_url") != entry["source_url"]]
    companies.append(entry)
    companies.sort(key=lambda c: c["company"].lower())
    data["metadata"] = METADATA
    data["companies"] = companies
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render(entry, parsed):
    lines = [f"{entry['company']}  ({parsed['reports'] or '?'} reportes) - {entry['source_url']}",
             f"{'Puesto':<52} {'Rango mensual':>22} {'Aportes':>7}"]
    for r in parsed["roles"]:
        lines.append(f"{r['role'][:52]:<52} {r['salary_text']:>22} {str(r['reports'] or '-'):>7}")
    lines.append("Montos estimados en soles mensuales (MyWorkIn, autodeclarados). Referencia, no escala oficial.")
    return "\n".join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("company", nargs="?", help="company name to look up")
    p.add_argument("--slug", help="MyWorkIn company slug (skips name matching and the index)")
    p.add_argument("--json", action="store_true", help="print the parsed result as JSON")
    p.add_argument("--no-save", action="store_true", help="do not write salary_data.json")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="salary JSON to merge into")
    p.add_argument("--refresh-index", action="store_true", help="refetch the company index now")
    args = p.parse_args(argv)

    if not args.company and not args.slug:
        p.error("give a company name or --slug")

    try:
        slug = args.slug or (ACRONYMS.get(args.company.strip().lower()) if args.company else None)
        if not slug:
            matches = best_matches(load_index(args.refresh_index), args.company)
            if not matches:
                print(f"No MyWorkIn salary page matches {args.company!r}.", file=sys.stderr)
                return 2
            # Ambiguous unless the best match is exact or clearly ahead: "Pacífico" scores
            # close for both Pacífico Seguros and Pacífico EPS, and guessing between two
            # employers would file the wrong pay data under the user's application.
            top_score = matches[0][0]
            ties = [c for s, c in matches if top_score < 100 and s >= top_score - 15]
            if len(ties) > 1:
                print(f"Several MyWorkIn companies match {args.company!r}; rerun with --slug:", file=sys.stderr)
                for c in ties[:8]:
                    print(f"  --slug {c['slug']:<40} {c['name']} ({c['reports'] or '?'} salarios)", file=sys.stderr)
                return 3
            slug = matches[0][1]["slug"]

        if not re.fullmatch(r"[a-z0-9-]+", slug):
            print(f"invalid slug {slug!r}", file=sys.stderr)
            return 1
        check_robots(f"/salaries/{slug}")
        page = http_get(f"{BASE}/salaries/{slug}")
        if page is None:
            print(f"MyWorkIn has no page /salaries/{slug}", file=sys.stderr)
            return 2
        parsed = parse_company(page)
        if not parsed["roles"]:
            print(f"No salary rows parsed from /salaries/{slug}; the page layout may have changed.", file=sys.stderr)
            return 1
    except FetchError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    entry = to_salary_entry(slug, parsed)
    if not args.no_save:
        merge(args.output, entry)
    if args.json:
        print(json.dumps({"slug": slug, **parsed, "source_url": entry["source_url"]}, ensure_ascii=False, indent=2))
    else:
        print(render(entry, parsed))
        if not args.no_save:
            print(f"Guardado en {args.output.name} (consulta: python salary_lookup.py \"{entry['company']}\")")
    return 0


if __name__ == "__main__":
    sys.exit(main())

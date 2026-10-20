#!/usr/bin/env python3
"""Employer logos for the review page, cached in company_research/logos/.

Sources, in order of trust:
  1. the posting itself: `companyLogo` in the portal CLIs' search and detail output
     (LinkedIn card or top card, Bumeran empresa.logoURL, Computrabajo detail page);
  2. MyWorkIn's salary index (tools/myworkin_salaries.py), matched by company name -
     only a close match, since a wrong logo is worse than none.

Every image is downloaded once, only from the hosts those sources use, capped in size,
decoded and re-encoded as a small PNG with Pillow (so the page never embeds bytes nobody
decoded), and recorded in company_research/logos/index.json with its source URL.
tools/pe_revision.py reads that index and embeds the PNGs inline, so the page stays a
single offline file.

Usage:
    python tools/pe_logos.py reports/detalles/*.json reports/busqueda/*.json
    python tools/pe_logos.py reports/detalles/*.json --state job_scraper/seen_jobs.json
    python tools/pe_logos.py ... --no-myworkin      # posting logos only
    python tools/pe_logos.py ... --refresh          # download again
"""

import argparse
import importlib.util
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = Path("company_research") / "logos"
INDEX = "index.json"
ALLOWED_HOSTS = {
    "media.licdn.com",
    "imgbum.jobscdn.com",
    "ii.ct-stc.com",
    "firebasestorage.googleapis.com",
}
MAX_BYTES = 2_000_000
SIZE = 96  # px, the longest side; shown at 28 px, so 3x for sharp screens
MIN_MATCH = 85  # MyWorkIn name match; below this a logo is more likely wrong than right
UA = "Mozilla/5.0 (compatible; pe-logos/1.0; personal job search)"


def company_file(name: str) -> str:
    """04-job-evaluation.md's cache filename rule, as tools/pe_revision.py applies it."""
    return re.sub(r"\s+", "-", (name or "").strip().lower())


def allowed(url) -> bool:
    if not isinstance(url, str):
        return False
    parts = urllib.parse.urlparse(url)
    return parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS


def walk(value):
    """Every dict inside a CLI output, a seen_jobs file, or a list of either."""
    if isinstance(value, dict):
        yield value
        for v in value.values():
            if isinstance(v, (dict, list)):
                yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


# Anonymous employers share one name across unrelated companies: never give them a logo.
GENERIC = re.compile(r"confidencial|importante empresa|empleador no divulgado|empresa confidencial", re.I)


def posting_logos(paths) -> dict[str, tuple[str, str]]:
    """company_file -> (company name as posted, logo URL) found on the postings themselves."""
    found: dict[str, tuple[str, str]] = {}
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for obj in walk(data):
            name, logo = obj.get("company"), obj.get("companyLogo")
            if isinstance(name, str) and name.strip() and not GENERIC.search(name) and allowed(logo):
                found.setdefault(company_file(name), (name, logo))
    return found


def load_matcher():
    spec = importlib.util.spec_from_file_location("salary_lookup", ROOT / "salary_lookup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.match_score


def fuzzy_posting_logo(match_score, posted: dict[str, tuple[str, str]], name: str) -> str | None:
    """A posting logo under a slightly different company name ("Banco Santander Perú" vs
    "Santander Perú"): the best match at MIN_MATCH or above."""
    best = max(((match_score(name, n), url) for n, url in posted.values()), default=(0, None))
    return best[1] if best[0] >= MIN_MATCH else None


def companies_in_state(path: Path) -> list[str]:
    try:
        seen = json.loads(path.read_text(encoding="utf-8")).get("seen", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    return sorted({e["company"] for e in seen.values()
                   if isinstance(e, dict) and isinstance(e.get("company"), str) and e.get("status") == "ranked"})


def load_myworkin():
    spec = importlib.util.spec_from_file_location("myworkin_salaries", ROOT / "tools" / "myworkin_salaries.py")
    mw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mw)
    companies = mw.load_index()
    if companies and not any("logo" in c for c in companies):
        companies = mw.load_index(refresh=True)  # cache written before logos were parsed
    return mw, companies


def myworkin_logo(mw, companies, name: str) -> str | None:
    matches = mw.best_matches(companies, name)
    if matches and matches[0][0] >= MIN_MATCH and allowed(matches[0][1].get("logo")):
        return matches[0][1]["logo"]
    return None


def to_png(raw: bytes) -> bytes:
    from PIL import Image  # optional dependency: only this tool needs it

    with Image.open(io.BytesIO(raw)) as img:
        img = img.convert("RGBA")
        img.thumbnail((SIZE, SIZE))
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        if not allowed(resp.geturl()):
            raise ValueError(f"redirected off the allowed hosts: {resp.geturl()}")
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("image too large")
    return raw


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="*", help="CLI search/detail JSON files (or seen_jobs.json)")
    ap.add_argument("--state", type=Path, default=Path("job_scraper/seen_jobs.json"),
                    help="ranked companies to look up on MyWorkIn when no posting carries a logo")
    ap.add_argument("--dir", type=Path, default=LOGO_DIR)
    ap.add_argument("--no-myworkin", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("pe_logos needs Pillow (pip install pillow)", file=sys.stderr)
        return 1

    args.dir.mkdir(parents=True, exist_ok=True)
    index_path = args.dir / INDEX
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {}

    posted = posting_logos(args.inputs)
    names = [n for n in companies_in_state(args.state) if not GENERIC.search(n)]
    wanted: dict[str, tuple[str, str, str]] = {}  # key -> (name, url, origin)
    if not names:  # no ranked jobs yet: cache every logo the postings carry
        wanted = {key: (name, url, "aviso") for key, (name, url) in posted.items()}
    match_score = load_matcher()
    mw = companies = None
    for name in names:
        key = company_file(name)
        if key in posted:
            wanted[key] = (name, posted[key][1], "aviso")
        elif url := fuzzy_posting_logo(match_score, posted, name):
            wanted[key] = (name, url, "aviso (nombre parecido)")
        elif not args.no_myworkin:
            if mw is None:
                mw, companies = load_myworkin()
            if url := myworkin_logo(mw, companies, name):
                wanted[key] = (name, url, "MyWorkIn")

    got = skipped = failed = 0
    for key, (name, url, origin) in sorted(wanted.items()):
        if key in index and not args.refresh and (args.dir / index[key]["file"]).is_file():
            skipped += 1
            continue
        try:
            png = to_png(download(url))
        except Exception as exc:  # one bad image never stops the run
            failed += 1
            print(f"  sin logo para {name}: {exc}", file=sys.stderr)
            continue
        file = re.sub(r"[^a-z0-9-]+", "_", key)[:80] + ".png"
        (args.dir / file).write_bytes(png)
        index[key] = {"file": file, "source": url, "origin": origin, "fetched": date.today().isoformat()}
        got += 1
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    missing = [n for n in names if company_file(n) not in index]
    print(f"logos: {got} nuevos, {skipped} ya estaban, {failed} fallaron; "
          f"{len(names) - len(missing)} de {len(names)} empresas evaluadas con logo")
    return 0


if __name__ == "__main__":
    sys.exit(main())

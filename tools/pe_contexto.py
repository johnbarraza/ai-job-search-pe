#!/usr/bin/env python3
"""Where a job is and what the employer does, with how sure we are of each.

For each posting (a portal CLI's `detail` JSON) it settles:

  lugar   the workplace district(s) and their Lima zone. The posting text wins when it
          names the workplace ("Sede Ate", "laborar en San Isidro"); then the district the
          employer picked on the portal; then an office found on the web and stored in
          company_research/<company>.json under "context". "Residir en ..." is a residence
          requirement, kept apart, never taken as the workplace.
  rubro   the employer's sector: the posting's own words ("empresa del rubro ..."), the
          portal's company field (Computrabajo/Bumeran `industry`, LinkedIn `industries`),
          or the web; and whether the publisher is a staffing or HR consultancy recruiting
          for an unnamed client, in which case the sector shown is the consultancy's.

Confidence: alta = the posting says it (or the portal and the posting agree); media = one
structured source (portal field, or a web source for a company with one office); baja =
inferred from the company name or a web office that may not be the workplace. Offline: web
findings are read from the research cache, never fetched here.

Usage:
    python tools/pe_contexto.py reports/detalles/*.json --json > reports/contexto.json
    python tools/pe_contexto.py reports/detalles/*.json            # table
"""

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pe_frescura", ROOT / "tools" / "pe_frescura.py")
pe_frescura = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe_frescura)

# Lima Metropolitana and Callao by the zones Peruvian market studies use (APEIM-style).
ZONES = {
    "Lima Norte": ["Ancón", "Carabayllo", "Comas", "Independencia", "Los Olivos", "Puente Piedra", "San Martín de Porres", "Santa Rosa"],
    "Lima Centro": ["Breña", "Cercado de Lima", "La Victoria", "Rímac", "San Luis"],
    "Lima Moderna": ["Barranco", "Jesús María", "La Molina", "Lince", "Magdalena del Mar", "Miraflores", "Pueblo Libre",
                     "San Borja", "San Isidro", "San Miguel", "Santiago de Surco", "Surquillo"],
    "Lima Este": ["Ate", "Chaclacayo", "Cieneguilla", "El Agustino", "Lurigancho", "San Juan de Lurigancho", "Santa Anita"],
    "Lima Sur": ["Chorrillos", "Lurín", "Pachacámac", "Pucusana", "Punta Hermosa", "Punta Negra", "San Bartolo",
                 "San Juan de Miraflores", "Santa María del Mar", "Villa El Salvador", "Villa María del Triunfo"],
    "Callao": ["Bellavista", "Callao", "Carmen de la Legua", "La Perla", "La Punta", "Mi Perú", "Ventanilla"],
    # Lima region, outside the metropolitan area: a daily commute from the city is long.
    "Fuera de Lima Metropolitana": ["Chilca", "Chancay", "Huaral", "Huacho", "Cañete", "Mala"],
}
ZONE_OF = {d: z for z, ds in ZONES.items() for d in ds}
ALIASES = {  # how postings write them -> canonical district
    "Surco": "Santiago de Surco", "SJL": "San Juan de Lurigancho", "SJM": "San Juan de Miraflores",
    "SMP": "San Martín de Porres", "VES": "Villa El Salvador", "VMT": "Villa María del Triunfo",
    "Magdalena": "Magdalena del Mar", "Lima Cercado": "Cercado de Lima", "Centro de Lima": "Cercado de Lima",
    "Ate Vitarte": "Ate", "Chosica": "Lurigancho", "Huachipa": "Lurigancho", "Jicamarca": "Lurigancho",
}
# Words that are also common nouns or names: matched only capitalized or all caps.
CASE_SENSITIVE = {"Ate", "Comas", "Independencia", "Santa Rosa", "Bellavista", "La Perla", "La Punta", "Lurigancho", "Callao"}
WORK_CUE = re.compile(r"(sede|laborar|trabajar|trabajo|ubicad|ubicaci|lugar|oficina|planta|distrito|almac|tienda|local|"
                      r"presencial|centro de operaciones|disponibilidad para|alt\.)", re.I)
HOME_CUE = re.compile(r"(residir|resida|vivir|viva|domicili|aleda|cercan)", re.I)

# Staffing / HR consultancies: the employer recruits or places staff for clients. Only names and
# sector labels that say so; a generic "consultoría" (IT, business) is not staffing.
STAFFING = re.compile(r"adecco|manpower|randstad|overall|eulen|lavoro|chamba ?talent|progesti|talenthia|arkana|"
                      r"recursos humanos|rrhh|human resources services|staffing|tercerizaci|intermediaci", re.I)
FOR_CLIENT = re.compile(r"(por encargo de (nuestro|un) cliente|nuestro cliente|para (el|la|los|nuestros) clientes?)", re.I)
# Text that shows the employer recruits for others, whatever its name or sector label.
RECRUITS_FOR_OTHERS = re.compile(r"(para|de) (diferentes|distintos|nuestros|varios) clientes|multicuentas|"
                                 r"terciarizaci[oó]n|intermediaci[oó]n laboral", re.I)
ANONYMOUS = re.compile(r"^\s*$|^confidencial$|importante empresa|empresa confidencial", re.I)
# Only phrases where the employer describes itself; "experiencia en el sector X" describes the candidate.
_X = r"([^.;:\n!¡]{3,80})"
SECTOR_PATTERNS = [
    re.compile(r"(?:empresa|compañ[ií]a|organizaci[oó]n|corporaci[oó]n|instituci[oó]n|grupo)\b[^.\n]{0,40}?"
               r"(?:del|en el) (?:rubro|sector|giro)(?: de(?:l)?)?\s+" + _X, re.I),
    re.compile(r"(?:empresa|compañ[ií]a)\b[^.\n]{0,25}?(?:dedicad[ao] (?:a|al)|especializad[ao] en)\s+" + _X, re.I),
    re.compile(r"\b(?:somos|es) una (?:importante |gran )?empresa de ([a-záéíóúñ]+(?: [a-záéíóúñ]+)?)", re.I),
]
_CUT = re.compile(r"\s+(?:con|que|y se|se encuentra|busca|actualmente|nos|para|desde|l[ií]der|reconocid[ao]|"
                  r"estamos|est[aá]|en la b[uú]squeda)\b|,\s*(?:se|actualmente|con|nos|est[aá])\b", re.I)
_JUNK = re.compile(r"^(?:el|la|su|los|las|nuestro|nuestra)\s+(?:sector|mercado|rubro|industria|pa[ií]s)\b", re.I)
GENERIC_INDUSTRY = re.compile(r"^(?:otra|otros|other|servicios)$", re.I)
LINKEDIN_ES = {
    "IT Services and IT Consulting": "servicios y consultoría de TI", "Staffing and Recruiting": "selección y dotación de personal",
    "Telephone Call Centers": "call centers", "Food and Beverage Manufacturing": "alimentos y bebidas",
    "Electric Power Transmission, Control, and Distribution": "transmisión y distribución eléctrica",
    "Human Resources Services": "servicios de recursos humanos", "Banking": "banca", "Retail": "retail",
    "Construction": "construcción", "Mining": "minería", "Financial Services": "servicios financieros",
    "Hospitals and Health Care": "salud", "Transportation, Logistics, Supply Chain and Storage": "transporte y logística",
    "Textile Manufacturing": "textil", "Truck Transportation": "transporte de carga", "Education": "educación",
    "Non-profit Organizations": "sin fines de lucro", "Higher Education": "educación superior",
    "Telecommunications": "telecomunicaciones", "Business Consulting and Services": "consultoría de negocios",
    "Manufacturing": "manufactura", "Insurance": "seguros", "Airlines and Aviation": "aviación",
    "Facilities Services": "servicios de facilities (limpieza, mantenimiento)", "Plastics Manufacturing": "plásticos",
}
NAME_HINTS = [  # last resort: the company's own name
    (r"aeroportuari", "servicios aeroportuarios"),
    (r"contratist|constructor|ingenier[ií]a y construc", "construcción"), (r"cl[ií]nica|salud|m[eé]dic", "salud"),
    (r"laboratorio", "laboratorio / farmacéutica"), (r"textil", "textil"), (r"transport|log[ií]stic|cargo", "transporte y logística"),
    (r"banco|financ|caja ", "banca y finanzas"), (r"seguridad|security", "seguridad privada"), (r"telecom|comunicaciones", "telecomunicaciones"),
    (r"miner", "minería"), (r"aliment|food|sandwich|pollos|restaurant", "alimentos y restaurantes"),
]


def unaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn")


def _district_patterns():
    names = {d: d for ds in ZONES.values() for d in ds}
    names.update(ALIASES)
    pats = []
    for written, canonical in sorted(names.items(), key=lambda kv: -len(kv[0])):  # longest first
        base = re.escape(unaccent(written)).replace(r"\ ", r"\s+")
        if written in CASE_SENSITIVE or written in ("SJL", "SJM", "SMP", "VES", "VMT"):
            pat = re.compile(rf"\b(?:{base}|{base.upper()})\b")
        else:
            pat = re.compile(rf"\b{base}\b", re.I)
        pats.append((pat, canonical))
    return pats


PATTERNS = _district_patterns()


def find_districts(text: str) -> dict[str, list[str]]:
    """Districts named in the text by role: "work" (a workplace cue such as "sede", "laborar en"
    sits right next to it), "home" (a residence requirement: "residir en ..."), and "mention"
    (named with no cue, e.g. where candidates are sourced). In order of appearance."""
    plain = unaccent(text or "")
    taken = [False] * len(plain)
    hits = []
    for pat, canonical in PATTERNS:
        for m in pat.finditer(plain):
            if any(taken[m.start():m.end()]):
                continue  # "San Juan de Lurigancho" already claimed "Lurigancho"
            for i in range(m.start(), m.end()):
                taken[i] = True
            # Cues count only within the district's own sentence.
            before = re.split(r"[.;\n!?]", plain[max(0, m.start() - 45):m.start()])[-1]
            after = re.split(r"[.;\n!?]", plain[m.end():m.end() + 25])[0]
            if HOME_CUE.search(before) and not WORK_CUE.search(before[-15:]):
                kind = "home"
            elif WORK_CUE.search(before) or WORK_CUE.search(after):
                kind = "work"
            else:
                kind = "mention"
            hits.append((m.start(), canonical, kind))
    out: dict[str, list[str]] = {"work": [], "home": [], "mention": []}
    for _, d, kind in sorted(hits):
        if d not in out[kind]:
            out[kind].append(d)
    return out


def portal_district(posting: dict) -> str | None:
    for raw in (posting.get("district"), (posting.get("location") or "").split(",")[0]):
        found = find_districts(raw or "")
        named = found["work"] + found["mention"]
        if named:
            return named[0]
    return None


def sector_from_text(text: str) -> str | None:
    """The employer's own description of its sector, or None."""
    for pat in SECTOR_PATTERNS:
        m = pat.search(text or "")
        if not m:
            continue
        phrase = _CUT.split(m.group(1).strip(), maxsplit=1)[0].strip(" ,-/").lower()
        phrase = re.sub(r"[,\s]+(?:y|e|o)$", "", phrase)
        if len(phrase) > 60:  # long lists of services: keep the first items, whole words
            phrase = phrase[:60].rsplit(" ", 1)[0].rstrip(" ,") + "…"
        if len(phrase) >= 3 and not _JUNK.match(phrase) and not phrase.isdigit():
            return phrase
    return None


def load_web(research_dir: Path, company: str) -> dict:
    path = research_dir / ((company or "").strip().lower().replace(" ", "-") + ".json")
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("context") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def analyze(posting: dict, research_dir: Path) -> dict:
    title, desc = posting.get("title") or "", posting.get("description") or ""
    company = posting.get("company") or ""
    text = f"{title}\n{desc}"
    web = load_web(research_dir, company)

    found = find_districts(text)
    in_title = [d for kind in ("work", "mention") for d in find_districts(title)[kind]]
    work = list(dict.fromkeys(in_title + found["work"]))
    p_district = portal_district(posting)
    offices = [o for o in (web.get("offices") or []) if o.get("district")]
    places_staff = bool(RECRUITS_FOR_OTHERS.search(desc))
    if work:
        lugar = {"districts": work, "source": "aviso", "confidence": "alta" if len(work) <= 3 else "media"}
    elif p_district and p_district in found["mention"]:
        lugar = {"districts": [p_district], "source": "aviso + portal", "confidence": "alta"}
    elif places_staff and found["mention"]:
        # An outsourcing firm's portal district is its own office; the job sits at the client
        # named in the text ("Analista ... BACKUS ATE").
        lugar = {"districts": found["mention"], "source": "aviso (sede del cliente)", "confidence": "media"}
    elif p_district:
        lugar = {"districts": [p_district], "source": "portal", "confidence": "media"}
    elif found["mention"] and posting.get("modality") != "remoto":
        lugar = {"districts": found["mention"], "source": "aviso", "confidence": "baja"}
    elif offices:
        lugar = {"districts": [o["district"] for o in offices], "source": "web",
                 "confidence": "media" if len(offices) == 1 and offices[0].get("is_workplace") else "baja",
                 "address": offices[0].get("address"), "url": offices[0].get("url")}
    else:
        lugar = {"districts": [], "source": None, "confidence": None}
    lugar["zones"] = sorted({ZONE_OF[d] for d in lugar["districts"] if d in ZONE_OF})
    if posting.get("address"):
        lugar["address"] = posting["address"]
    lugar["residence_required"] = found["home"]
    lugar["remote"] = posting.get("modality") == "remoto"
    if lugar["remote"] and lugar["districts"]:
        lugar["confidence"] = "baja"  # the work is from home; these are the employer's or sourcing areas

    raw_industry = posting.get("industry") or LINKEDIN_ES.get(posting.get("industries") or "", posting.get("industries"))
    portal_sector = None if raw_industry and GENERIC_INDUSTRY.match(raw_industry.strip()) else raw_industry
    text_sector = sector_from_text(desc) or sector_from_text(title)
    web_sector = (web.get("sector") or {}).get("label")
    staffing = bool(STAFFING.search(f"{company} | {portal_sector or ''} | {text_sector or ''}")) or places_staff
    for_client = staffing and bool(FOR_CLIENT.search(desc))
    anonymous = bool(ANONYMOUS.search(company))
    if text_sector and portal_sector and (unaccent(text_sector.split()[0]).lower() in unaccent(portal_sector).lower()):
        rubro = {"label": portal_sector, "source": "aviso + portal", "confidence": "alta"}
    elif text_sector:
        rubro = {"label": text_sector, "source": "aviso", "confidence": "alta"}
    elif portal_sector:
        rubro = {"label": portal_sector, "source": "portal", "confidence": "media"}
    elif web_sector:
        rubro = {"label": web_sector, "source": "web", "confidence": (web.get("sector") or {}).get("confidence", "media"),
                 "url": (web.get("sector") or {}).get("url")}
    elif staffing:
        rubro = {"label": "consultora de selección o de personal", "source": "aviso", "confidence": "media"}
    else:
        guess = next((label for pat, label in NAME_HINTS if re.search(pat, company, re.I)), None)
        rubro = {"label": guess, "source": "nombre" if guess else None, "confidence": "baja" if guess else None}
    rubro["staffing"] = staffing
    rubro["for_client"] = for_client
    rubro["anonymous"] = anonymous

    return {
        "id": posting.get("id"), "url": posting.get("url"), "company": company, "title": title,
        "portal": pe_frescura.portal_of(posting.get("url") or ""), "lugar": lugar, "rubro": rubro,
        "links": company_links(posting, web, anonymous),
    }


def company_links(posting: dict, web: dict, anonymous: bool) -> dict:
    """Where to read about the employer: its own site (from the research cache only, never
    guessed), its LinkedIn page and its Computrabajo profile when the portal gives them."""
    links = {}
    url = posting.get("companyUrl") or ""
    if re.match(r"^https?://([a-z]+\.)?linkedin\.com/company/", url):
        links["linkedin"] = url
    elif re.match(r"^https?://pe\.computrabajo\.com/", url):
        links["computrabajo"] = url
    for key in ("website", "linkedin"):
        value = web.get(key)
        if isinstance(value, str) and re.match(r"^https?://", value):
            links[key] = value
    if anonymous:
        links.pop("computrabajo", None)  # an anonymous posting's link is the portal's, not a company's
    return links


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path, help="portal CLI detail JSON files")
    ap.add_argument("--research", type=Path, default=Path("company_research"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rows = []
    for path in args.files:
        try:
            for posting in pe_frescura.load_postings(path):
                rows.append(analyze(posting, args.research))
        except (OSError, ValueError) as exc:
            print(f"cannot read {path}: {exc}", file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps({"postings": rows}, ensure_ascii=False, indent=2))
        return 0
    for r in rows:
        lg, rb = r["lugar"], r["rubro"]
        where = ("remoto · " if lg["remote"] else "") + (", ".join(lg["districts"]) or "sin dato")
        zone = f" ({', '.join(lg['zones'])})" if lg["zones"] else ""
        sector = rb["label"] or "sin identificar"
        tags = "".join([" · consultora" if rb["staffing"] else "", " · para un cliente" if rb["for_client"] else "",
                        " · empresa anónima" if rb["anonymous"] else ""])
        print(f"{(r['company'] or '—')[:28]:<28} | {where}{zone} [{lg['source'] or '—'}, {lg['confidence'] or '—'}] | "
              f"{sector} [{rb['source'] or '—'}, {rb['confidence'] or '—'}]{tags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for tools/pe_contexto.py: workplace district, Lima zone and employer sector (Peru fork)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pe_contexto", REPO / "tools" / "pe_contexto.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

CT = "https://pe.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-{}"


def posting(**over):
    base = {"id": "A" * 32, "url": CT.format("A" * 32), "company": "Acme", "title": "Asistente de Selección",
            "description": "", "location": "Lima, Lima", "modality": "presencial"}
    base.update(over)
    return base


def run(p, research=None):
    return pc.analyze(p, Path(research or tempfile.mkdtemp()))


class Districts(unittest.TestCase):
    def test_workplace_cue_beats_a_bare_mention_and_residence_is_kept_apart(self):
        found = pc.find_districts("Disponibilidad para laborar en San Isidro. Residir en SJM o zonas aledañas. "
                                  "Clientes en Miraflores.")
        self.assertEqual(found["work"], ["San Isidro"])
        self.assertEqual(found["home"], ["San Juan de Miraflores"])
        self.assertEqual(found["mention"], ["Miraflores"])

    def test_aliases_and_longest_name_first(self):
        found = pc.find_districts("Sede Surco y planta en San Juan de Lurigancho")
        self.assertEqual(found["work"], ["Santiago de Surco", "San Juan de Lurigancho"])

    def test_common_words_only_match_capitalized(self):
        self.assertEqual(pc.find_districts("separado por comas, con independencia")["mention"], [])
        self.assertEqual(pc.find_districts("Sede Comas")["work"], ["Comas"])

    def test_zone_of_each_district(self):
        lugar = run(posting(title="Asistente - Sede Ate"))["lugar"]
        self.assertEqual((lugar["districts"], lugar["zones"], lugar["source"]), (["Ate"], ["Lima Este"], "aviso"))

    def test_lima_region_outside_the_metropolitan_area_has_its_own_zone(self):
        lugar = run(posting(description="Sede de Trabajo: Chilca (3 días) y V.E.S (2 días)"))["lugar"]
        self.assertIn("Chilca", lugar["districts"])
        self.assertIn("Fuera de Lima Metropolitana", lugar["zones"])


class Place(unittest.TestCase):
    def test_portal_district_when_the_text_is_silent(self):
        lugar = run(posting(location="Santiago de Surco, Lima"))["lugar"]
        self.assertEqual((lugar["districts"], lugar["source"], lugar["confidence"]), (["Santiago de Surco"], "portal", "media"))

    def test_an_outsourcing_firm_works_at_the_client_named_in_the_text(self):
        p = posting(company="Lavoro Perú", location="Surco, Lima",
                    description="Empresa destacada en el rubro de terciarización e intermediación laboral. "
                                "Puesto de ANALISTA DE RECURSOS HUMANOS BACKUS ATE.")
        lugar = run(p)["lugar"]
        self.assertEqual((lugar["districts"], lugar["source"]), (["Ate"], "aviso (sede del cliente)"))

    def test_remote_postings_keep_named_districts_at_low_confidence(self):
        lugar = run(posting(modality="remoto", description="Captar candidatos para la planta de Lurín"))["lugar"]
        self.assertTrue(lugar["remote"])
        self.assertEqual(lugar["confidence"], "baja")

    def test_web_office_from_the_research_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "acme.json").write_text(json.dumps({"context": {"offices": [
                {"district": "Miraflores", "address": "Av. Larco 1", "url": "https://acme.pe", "is_workplace": True}]}}),
                encoding="utf-8")
            lugar = run(posting(), tmp)["lugar"]
        self.assertEqual((lugar["districts"], lugar["source"], lugar["confidence"], lugar["address"]),
                         (["Miraflores"], "web", "media", "Av. Larco 1"))


class Address(unittest.TestCase):
    def test_street_addresses_and_corners_from_the_text(self):
        self.assertEqual(pc.address_from_text("Ubicación: Av. Javier Prado Este 4200, Lima. Horario de 9 a 6"), "Av. Javier Prado Este 4200")
        self.assertEqual(pc.address_from_text("sede Magdalena (Alt. Salaverry con Pershing)."), "Alt. Salaverry con Pershing")
        self.assertEqual(pc.address_from_text("Planta en Carretera Central Km 15.5 - Ate"), "Carretera Central Km 15.5")

    def test_prose_and_residence_are_not_addresses(self):
        self.assertIsNone(pc.address_from_text("Calle a calle buscamos talento"))
        self.assertIsNone(pc.address_from_text("Residir cerca de Av. Túpac Amaru 1200"))

    def test_the_address_reaches_the_place(self):
        lugar = run(posting(description="Laborar en nuestra sede de Av. Javier Prado Este 4200, San Borja."))["lugar"]
        self.assertEqual(lugar["address"], "Av. Javier Prado Este 4200, San Borja")  # the district helps the map


class Sector(unittest.TestCase):
    def test_the_employer_describing_itself_is_high_confidence(self):
        rubro = run(posting(description="Somos una empresa del sector ingeniería, electricidad y construcción, "
                                        "se encuentra en la búsqueda de..."))["rubro"]
        self.assertEqual((rubro["label"], rubro["source"], rubro["confidence"]),
                         ("ingeniería, electricidad y construcción", "aviso", "alta"))

    def test_experience_asked_of_the_candidate_is_not_the_employer_sector(self):
        rubro = run(posting(description="Experiencia en el sector financiero. Deseable rubro industrial."))["rubro"]
        self.assertIsNone(rubro["label"])

    def test_vague_phrases_are_dropped(self):
        self.assertIsNone(pc.sector_from_text("Somos una empresa líder en el sector, con 10 años"))

    def test_portal_field_and_generic_labels(self):
        self.assertEqual(run(posting(industry="Construcción"))["rubro"]["source"], "portal")
        self.assertIsNone(run(posting(industry="Otra"))["rubro"]["label"])

    def test_staffing_consultancies_and_anonymous_employers(self):
        adecco = run(posting(company="Adecco Perú S.A.", industry="Servicios Profesionales"))["rubro"]
        self.assertTrue(adecco["staffing"])
        it = run(posting(company="Encora Inc.", industries="IT Services and IT Consulting"))["rubro"]
        self.assertFalse(it["staffing"])  # an IT consultancy is not a staffing firm
        self.assertEqual(it["label"], "servicios y consultoría de TI")
        anon = run(posting(company="Importante empresa del sector"))["rubro"]
        self.assertTrue(anon["anonymous"])

    def test_company_name_as_last_resort(self):
        rubro = run(posting(company="Talma Servicios Aeroportuarios"))["rubro"]
        self.assertEqual((rubro["label"], rubro["source"], rubro["confidence"]), ("servicios aeroportuarios", "nombre", "baja"))


class Links(unittest.TestCase):
    def test_company_pages_from_the_portal_and_the_cache_only(self):
        li = run(posting(companyUrl="https://www.linkedin.com/company/encorainc"))["links"]
        self.assertEqual(li, {"linkedin": "https://www.linkedin.com/company/encorainc"})
        ct = run(posting(companyUrl="https://pe.computrabajo.com/adecco"))["links"]
        self.assertEqual(ct, {"computrabajo": "https://pe.computrabajo.com/adecco"})
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "acme.json").write_text(json.dumps({"context": {"website": "https://acme.pe", "linkedin": "javascript:x"}}),
                                                 encoding="utf-8")
            self.assertEqual(run(posting(), tmp)["links"], {"website": "https://acme.pe"})

    def test_anonymous_postings_get_no_company_profile_link(self):
        links = run(posting(company="Importante empresa del sector", companyUrl="https://pe.computrabajo.com/x"))["links"]
        self.assertEqual(links, {})


class Cli(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"
            path.write_text(json.dumps(posting(title="Asistente - Sede Ate")), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(REPO / "tools" / "pe_contexto.py"), str(path), "--json",
                                   "--research", str(Path(tmp) / "none")], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["postings"][0]["lugar"]["districts"], ["Ate"])


if __name__ == "__main__":
    unittest.main()

"""tools/pe_duplicados.py: one posting published on several portals."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pe_duplicados", REPO / "tools" / "pe_duplicados.py")
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)

BODY = ("Participar activamente en la evolucion del modelo de datos de riesgos, migracion del modelo on premise "
        "a cloud, procesos de extraccion transformacion y carga, monitoreo del portafolio con indicadores de riesgo, "
        "requisitos estudiante octavo ciclo ingenieria sistemas computacion SQL server consultas stored procedures "
        "funciones Power BI avanzado herramientas ETL SSIS Datatools Knime lenguajes programacion Python Java nube "
        "Azure AWS beneficios bienestar salud seguro capacitacion linea carrera horario flexible oficina San Isidro")
BOILER = ("Who we are Boston Consulting Group partners with leaders in business and society to tackle their most "
          "important challenges and capture their greatest opportunities pioneer in business strategy founded 1963 "
          "total transformation inspiring complex change enabling organizations grow building competitive advantage "
          "driving bottom line impact digital human capabilities diverse global teams deep industry functional expertise")


def entry(company, title, url, score=70):
    return {"company": company, "title": title, "url": url, "status": "ranked", "rank_score": score}


class Find(unittest.TestCase):
    def details(self, *pairs):
        return {pd.posting_id({"url": url}): {"description": text} for url, text in pairs}

    def test_an_intermediary_reposting_the_same_text_is_a_duplicate(self):
        seen = {
            "bm": entry("Santander Perú", "Practicante Pre-Profesional de Riesgo",
                        "https://www.bumeran.com.pe/empleos/x-1118470437.html", 53),
            "li": entry("Universia Perú", "Practicante Pre-Profesional Riesgos - Santander Consumer Bank",
                        "https://www.linkedin.com/jobs/view/4475140001", 53),
        }
        det = self.details((seen["bm"]["url"], "Santander Consumer Bank busca talento " + BODY), (seen["li"]["url"], BODY))
        pairs = pd.find(seen, det)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][1], "li")  # same score: the fuller description stays

    def test_two_roles_sharing_company_boilerplate_are_not_duplicates(self):
        seen = {
            "a": entry("BCG", "Associate, Peru", "https://www.linkedin.com/jobs/view/4409721468"),
            "b": entry("BCG", "Associates, Internship, Peru", "https://www.linkedin.com/jobs/view/4321447425"),
        }
        det = self.details((seen["a"]["url"], BOILER), (seen["b"]["url"], BOILER))
        self.assertEqual(pd.find(seen, det), [])

    def test_different_areas_of_one_company_are_not_duplicates(self):
        seen = {
            "f": entry("astara", "Practicante Pre Profesional de Finanzas", "https://www.linkedin.com/jobs/view/4478545960"),
            "e": entry("astara", "Practicante Pre Profesional de Estrategia y Negocios", "https://www.linkedin.com/jobs/view/4476946312"),
        }
        det = self.details((seen["f"]["url"], BODY), (seen["e"]["url"], BODY))
        self.assertEqual(pd.find(seen, det), [])

    def test_write_records_and_a_rerun_clears_stale_marks(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "seen.json"
            seen = {"x": entry("Acme", "Practicante de Datos", "https://www.linkedin.com/jobs/view/1111111"),
                    "y": dict(entry("Acme", "Practicante de Datos", "https://www.linkedin.com/jobs/view/2222222"),
                              duplicate_of="z")}
            state.write_text(json.dumps({"seen": seen}), encoding="utf-8")
            pd.main(["/nonexistent.json", "--state", str(state), "--write"])
            self.assertNotIn("duplicate_of", json.loads(state.read_text(encoding="utf-8"))["seen"]["y"])


if __name__ == "__main__":
    unittest.main()

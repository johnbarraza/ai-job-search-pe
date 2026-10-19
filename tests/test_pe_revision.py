"""Tests for tools/pe_revision.py: the review page built from the workflow's files (Peru fork)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pe_revision", REPO / "tools" / "pe_revision.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

BM_SEARCH = "https://www.bumeran.com.pe/empleos/asistente-de-seleccion-acme-1118482096.html"
BM_DETAIL = "https://www.bumeran.com.pe/empleos/asistente-de-seleccion-acme-s-a-1118482096.html"


def ranked(**over):
    base = {
        "title": "Asistente de Selección", "company": "Acme", "url": BM_SEARCH, "status": "ranked",
        "rank_score": 70, "rank_verdict": "Good Fit", "location_verdict": "PASS", "language_gate": "PASS",
        "modality": "híbrido", "level": "asistente", "portal": "bumeran-search",
        "strengths": ["1 año en R&S"], "gaps": ["Pide bachiller"],
    }
    base.update(over)
    return base


class Actions(unittest.TestCase):
    def test_shortlist_actions_follow_freshness(self):
        good = ranked()
        self.assertEqual(pr.action_for(good, {"risk": "bajo", "window": "fresca"}), "ya")
        self.assertEqual(pr.action_for(good, {"risk": "bajo", "window": "en curso"}), "pronto")
        self.assertEqual(pr.action_for(good, {"risk": "medio", "window": "vieja"}), "confirmar")
        self.assertEqual(pr.action_for(good, {"risk": "alto", "window": "muy vieja"}), "antes")
        self.assertEqual(pr.action_for(good, None), "pronto")  # freshness not checked: no promise of "ya"

    def test_lower_verdicts_and_vetoes(self):
        self.assertEqual(pr.action_for(ranked(rank_verdict="Moderate Fit"), None), "tiempo")
        self.assertEqual(pr.action_for(ranked(rank_verdict="Weak Fit"), None), "descartar")
        self.assertEqual(pr.action_for(ranked(location_verdict="FAIL"), {"risk": "bajo", "window": "fresca"}), "descartar")
        self.assertEqual(pr.action_for(ranked(language_gate="FAIL"), None), "descartar")


class Ratings(unittest.TestCase):
    def test_missing_research_and_missing_ratings_read_differently(self):
        self.assertIn("sin investigar", pr.rating_html(None))
        self.assertIn("no es mala señal", pr.rating_html([]))

    def test_every_rating_shows_its_count_and_small_or_missing_counts_are_referential(self):
        big = pr.rating_html([{"source": "Computrabajo", "rating": 4.26, "n": 20188, "area": "Recursos Humanos", "area_n": 12}])
        self.assertIn("4,26", big)
        self.assertIn("n=20.188", big)
        self.assertIn("12 opiniones · referencial", big)
        self.assertNotIn('<span class="tag">referencial</span>', big)
        small = pr.rating_html([{"source": "Indeed", "rating": 4.0, "n": 12}])
        self.assertIn("referencial", small)
        self.assertIn("<b>4,0</b>", small)
        self.assertEqual(pr.fmt_rating(3.9), "3,9")
        no_n = pr.rating_html([{"source": "Computrabajo", "rating": 4.2, "n": None}])
        self.assertIn("sin n", no_n)
        self.assertIn("referencial", no_n)


class Rendering(unittest.TestCase):
    def build(self, seen, fresh=(), research=None):
        tmp = Path(tempfile.mkdtemp())
        research_dir = tmp / "company_research"
        research_dir.mkdir()
        for name, doc in (research or {}).items():
            (research_dir / pr.company_file(name)).write_text(json.dumps(doc), encoding="utf-8")
        data = pr.collect({"seen": seen}, list(fresh), research_dir)
        return data, pr.render(data, date(2026, 10, 18), "Prueba")

    def test_freshness_joins_on_the_posting_id_even_when_urls_differ(self):
        data, page = self.build(
            {"k": ranked()},
            fresh=[{"url": BM_DETAIL, "risk": "bajo", "window": "fresca", "age_days": 3, "signals": [], "original_date": "2026-10-15"}],
        )
        self.assertEqual(data["ranked"][0]["action"], "ya")
        self.assertIn("publicada 2026-10-15", page)

    def test_values_from_the_state_are_escaped_and_only_http_links_render(self):
        evil = ranked(company='<script>alert(1)</script>', title='T "x"', url="javascript:alert(1)",
                      gaps=["<img src=x onerror=alert(1)>"])
        _, page = self.build({"k": evil})
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('href="javascript:', page)
        self.assertNotIn("<img src=x", page)

    def test_order_sections_and_flow_counts(self):
        seen = {
            "a": ranked(rank_score=60),
            "b": ranked(rank_score=74, url="https://www.linkedin.com/jobs/view/4476949303", company="B"),
            "c": ranked(rank_verdict="Poor Fit", rank_score=20, company="C", url="https://www.linkedin.com/jobs/view/1"),
            "d": {"title": "Sin evaluar", "company": "D", "url": "https://x.example/1", "status": "new", "fit": "medium", "posted_date": "2026-10-17"},
            "e": {"title": "Irrelevante", "company": "E", "url": "https://x.example/2", "status": "new", "fit": "low"},
        }
        data, page = self.build(seen, research={"B": {"sources": {"reviews": {"ratings": [{"source": "Computrabajo", "rating": 4.1, "n": 200}]}}}})
        self.assertEqual([r["key"] for r in data["ranked"]], ["b", "a", "c"])
        self.assertEqual([r["key"] for r in data["unranked"]], ["d"])
        self.assertEqual(data["rated"], 1)
        self.assertIn("Para decidir (2)", page)
        self.assertIn("Descartadas o no elegibles (1)", page)
        self.assertIn("sin evaluar (1)", page)


class Cli(unittest.TestCase):
    def test_writes_the_page_without_freshness_or_research(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "seen.json").write_text(json.dumps({"seen": {"k": ranked()}}), encoding="utf-8")
            out = tmp / "r" / "revision.html"
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "pe_revision.py"), "--state", str(tmp / "seen.json"),
                 "--frescura", str(tmp / "none.json"), "--research", str(tmp / "none"), "--out", str(out),
                 "--today", "2026-10-18"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("1 evaluadas", proc.stdout)
            page = out.read_text(encoding="utf-8")
            self.assertTrue(page.startswith("<!doctype html>"))
            self.assertNotIn("http://cdn", page)
            self.assertNotIn("<script src", page)


class ArtifactMode(unittest.TestCase):
    def test_artifact_mode_drops_the_wrapper_and_declares_the_gutter(self):
        data = pr.collect({"seen": {"k": ranked()}}, [], Path(tempfile.mkdtemp()))
        page = pr.render(data, date(2026, 10, 18), "César", artifact=True)
        self.assertTrue(page.startswith("<title>Ofertas de César</title>"))
        for tag in ("<!doctype", "<html", "<head>", "<body", "</body>"):  # "<head" would match <header>
            self.assertNotIn(tag, page.lower())
        self.assertIn('<meta name="claude:viewport-fit-sides" content="cover">', page)
        self.assertIn("max(16px,env(safe-area-inset-left,0px))", page)

    def test_both_modes_follow_the_host_theme_toggle(self):
        data = pr.collect({"seen": {}}, [], Path(tempfile.mkdtemp()))
        for artifact in (False, True):
            page = pr.render(data, date(2026, 10, 18), None, artifact=artifact)
            self.assertIn(':root:not([data-theme="light"])', page)
            self.assertIn(':root[data-theme="dark"]', page)
            self.assertIn("tr.hidden=!ok", page)


if __name__ == "__main__":
    unittest.main()

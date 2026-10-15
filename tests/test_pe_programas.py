"""Tests for tools/pe_programas.py and the registry it reads (Peru fork)."""
import importlib.util
import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pe_programas", REPO / "tools" / "pe_programas.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)
rs_spec = importlib.util.spec_from_file_location("rank_state", REPO / "tools" / "rank_state.py")
rank_state = importlib.util.module_from_spec(rs_spec)
rs_spec.loader.exec_module(rank_state)

REGISTRY = json.loads((REPO / "data" / "peru" / "programas_extension.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 15)


def prog(**over):
    base = {
        "id": "x", "institution": "X", "program": "PEU", "url": "https://example.gob.pe/peu",
        "careers": ["Economía"], "modality": "remoto", "level": "programa de extensión",
        "status": "abierta", "inscription_open": "2026-09-01", "inscription_close": "2026-10-20",
        "verified_on": "2026-10-15", "sources": ["https://example.gob.pe/peu"],
    }
    base.update(over)
    return base


class Registry(unittest.TestCase):
    """The checked-in registry is data other commands present as fact: keep it well formed."""

    def test_entries_are_complete_and_use_the_shared_vocabulary(self):
        ids = set()
        for p in REGISTRY["programs"]:
            with self.subTest(p["id"]):
                self.assertNotIn(p["id"], ids)
                ids.add(p["id"])
                for key in ("institution", "program", "url", "careers", "status", "verified_on", "sources"):
                    self.assertTrue(p.get(key), f"missing {key}")
                self.assertIn(p["status"], {"abierta", "por_confirmar", "cerrada"})
                self.assertIn(p["modality"], rank_state.MODALITIES)
                self.assertIn(p["level"], rank_state.LEVELS)
                self.assertTrue(p["url"].startswith("https://"))
                for key in ("inscription_open", "inscription_close", "exam", "verified_on"):
                    if p.get(key):
                        date.fromisoformat(p[key])

    def test_an_open_call_always_has_a_closing_date(self):
        for p in REGISTRY["programs"]:
            if p["status"] == "abierta":
                self.assertTrue(p.get("inscription_close"), p["id"])

    def test_unconfirmed_calls_carry_no_closing_date(self):
        """A date nobody verified must not look like a fact in the output."""
        for p in REGISTRY["programs"]:
            if p["status"] == "por_confirmar":
                self.assertIsNone(p.get("inscription_close"), p["id"])


class Annotate(unittest.TestCase):
    def test_days_left_and_urgency(self):
        r = pp.annotate(prog(inscription_close="2026-10-20"), TODAY)
        self.assertEqual((r["days_left"], r["urgent"], r["effective_status"]), (5, True, "abierta"))
        self.assertFalse(pp.annotate(prog(inscription_close="2026-11-30"), TODAY)["urgent"])

    def test_a_passed_deadline_closes_the_call(self):
        r = pp.annotate(prog(inscription_close="2026-10-01"), TODAY)
        self.assertEqual((r["effective_status"], r["days_left"]), ("cerrada", None))

    def test_a_future_opening_is_por_abrir(self):
        r = pp.annotate(prog(inscription_open="2026-11-01", inscription_close="2026-12-01"), TODAY)
        self.assertEqual(r["effective_status"], "por_abrir")

    def test_old_verification_is_flagged(self):
        self.assertTrue(pp.annotate(prog(verified_on="2026-08-01"), TODAY)["stale"])
        self.assertFalse(pp.annotate(prog(verified_on="2026-10-10"), TODAY)["stale"])


class Select(unittest.TestCase):
    PROGRAMS = [
        prog(id="late", institution="B", inscription_close="2026-11-30"),
        prog(id="soon", institution="A", inscription_close="2026-10-20"),
        prog(id="tbc", institution="C", status="por_confirmar", inscription_close=None),
        prog(id="gone", institution="D", inscription_close="2026-09-01"),
        prog(id="law", institution="E", careers=["Derecho"], inscription_close="2026-10-25"),
    ]

    def test_open_first_by_deadline_then_unconfirmed_and_closed_hidden(self):
        ids = [r["id"] for r in pp.select(self.PROGRAMS, TODAY, False, None)]
        self.assertEqual(ids, ["soon", "law", "late", "tbc"])

    def test_all_includes_closed(self):
        self.assertIn("gone", [r["id"] for r in pp.select(self.PROGRAMS, TODAY, True, None)])

    def test_career_filter_ignores_accents_and_case(self):
        ids = [r["id"] for r in pp.select(self.PROGRAMS, TODAY, False, "ECONOMIA")]
        self.assertNotIn("law", ids)


class Cli(unittest.TestCase):
    def test_json_output_on_a_legacy_console(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools" / "pe_programas.py"), "--json", "--today", "2026-10-15"],
            capture_output=True,
            env={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(data["today"], "2026-10-15")
        self.assertTrue(all(r["effective_status"] != "cerrada" for r in data["programs"]))


if __name__ == "__main__":
    unittest.main()

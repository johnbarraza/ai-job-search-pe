"""Tests for tools/pe_frescura.py: posting freshness and ghost-job risk (Peru fork)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pe_frescura", REPO / "tools" / "pe_frescura.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

TODAY = date(2026, 10, 18)
CT = "https://pe.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-{}"
BM = "https://www.bumeran.com.pe/empleos/aviso-{}.html"


def ct(id_="7937C7D84CBBA71461373E686DCF3405", **over):
    base = {"id": id_, "title": "Asistente", "company": "Acme", "url": CT.format(id_), "date": "2026-10-15"}
    base.update(over)
    return base


def bm_run():
    """A day-by-day run of Bumeran ids rising ~1,500 a day, like the live portal in October 2026."""
    rows = []
    for offset, day in enumerate(range(5, 17)):
        for k in range(3):
            pid = 1118460000 + offset * 1500 + k * 100
            rows.append({"id": str(pid), "title": f"T{pid}", "company": "C", "url": BM.format(pid), "date": f"2026-10-{day:02d}"})
    return rows


def one(posting, calibration=()):
    return pf.evaluate([posting], list(calibration), TODAY)[0]


class Windows(unittest.TestCase):
    def test_a_fresh_posting_is_low_risk_and_says_apply_now(self):
        row = one(ct(date="2026-10-15"))
        self.assertEqual((row["window"], row["risk"], row["age_days"]), ("fresca", "bajo", 3))
        self.assertIn("postula ya", row["advice"])

    def test_age_counts_from_the_original_publication_not_the_renewal(self):
        # Austral Group, live: published 16 Sep, renewed 10 Oct, shown as recent in search.
        row = one(ct(date="2026-09-16", updated="2026-10-10", validThrough="2026-11-15"))
        self.assertEqual(row["age_days"], 32)
        self.assertEqual((row["window"], row["risk"]), ("vieja", "medio"))
        self.assertIn("renovada el 2026-10-10", row["signals"])

    def test_a_renewal_alone_does_not_raise_the_risk(self):
        row = one(ct(date="2026-10-12", updated="2026-10-17"))
        self.assertEqual(row["risk"], "bajo")

    def test_very_old_postings_are_high_risk(self):
        self.assertEqual(one(ct(date="2026-08-20"))["risk"], "alto")

    def test_missing_date_is_reported_not_guessed(self):
        row = one(ct(date=None))
        self.assertEqual((row["window"], row["age_days"], row["risk"]), ("sin fecha", None, "bajo"))


class ClosedAndExpired(unittest.TestCase):
    def test_linkedin_closed_banner_is_high_risk(self):
        row = one({"id": "4470996313", "url": "https://www.linkedin.com/jobs/view/4470996313", "date": "2026-10-15", "isActive": False})
        self.assertEqual(row["risk"], "alto")
        self.assertIn("cerrada en el portal", row["signals"])

    def test_bumeran_state_other_than_activo_is_closed(self):
        row = one({"id": "1", "url": BM.format(1), "date": "2026-10-15", "status": "finalizado"})
        self.assertEqual(row["risk"], "alto")

    def test_portal_expiry_in_the_past_is_high_risk_and_soon_is_flagged(self):
        self.assertEqual(one(ct(validThrough="2026-10-01"))["risk"], "alto")
        self.assertTrue(any("retira" in s for s in one(ct(validThrough="2026-10-22"))["signals"]))


class Reposts(unittest.TestCase):
    def test_linkedin_reposted_label_is_medium_risk(self):
        row = one({"id": "1", "url": "https://www.linkedin.com/jobs/view/1", "date": "2026-10-14", "reposted": True})
        self.assertEqual(row["risk"], "medio")

    def test_an_old_sequential_id_reveals_a_republished_aviso(self):
        # C. Mejía, live: Bumeran id 1118384615 shown as published 13 Oct among ids
        # ~90,000 higher - an aviso created about two months earlier.
        old = {"id": "1118384615", "title": "Asistente R&S", "company": "C. Mejía", "url": BM.format(1118384615), "date": "2026-10-13"}
        row = one(old, bm_run())
        self.assertEqual(row["risk"], "alto")  # its real age is past OLD_DAYS
        self.assertTrue(any("republicado" in s for s in row["signals"]))
        self.assertLess(date.fromisoformat(row["id_created_estimate"]), date(2026, 9, 1))

    def test_an_id_in_line_with_its_date_is_not_flagged(self):
        normal = {"id": "1118472000", "title": "X", "company": "Y", "url": BM.format(1118472000), "date": "2026-10-13"}
        row = one(normal, bm_run())
        self.assertFalse(any("republicado" in s for s in row["signals"]))
        self.assertEqual(row["risk"], "bajo")

    def test_no_calibration_means_no_id_estimate(self):
        row = one({"id": "1118384615", "url": BM.format(1118384615), "date": "2026-10-13"})
        self.assertIsNone(row["id_created_estimate"])

    def test_computrabajo_ids_are_not_sequential_and_never_dated(self):
        self.assertIsNone(pf.numeric_id(ct(), "computrabajo"))

    def test_the_same_role_posted_several_times_is_reported(self):
        copies = [ct(id_=f"{i:032X}", company="Impulsate", title="Supervisor de campo WIN") for i in range(3)]
        row = pf.evaluate(copies[:1], copies[1:], TODAY)[0]
        self.assertTrue(any("3 veces" in s for s in row["signals"]))

    def test_a_detail_and_its_seen_jobs_entry_are_one_posting_not_two(self):
        detail = ct()
        seen = {"title": detail["title"], "company": detail["company"], "url": detail["url"], "date": detail["date"]}
        row = pf.evaluate([detail], [seen], TODAY)[0]
        self.assertFalse(any("veces" in s for s in row["signals"]))


class Applicants(unittest.TestCase):
    def test_many_applicants_raise_the_risk_and_counts_are_shown(self):
        many = one({"id": "1", "url": "https://www.linkedin.com/jobs/view/1", "date": "2026-10-16", "applicants": 200, "applicantsText": "Over 200 applicants"})
        self.assertEqual(many["risk"], "medio")
        few = one({"id": "2", "url": "https://www.linkedin.com/jobs/view/2", "date": "2026-10-16", "applicants": 49})
        self.assertIn("49 postulantes", few["signals"])
        early = one({"id": "3", "url": "https://www.linkedin.com/jobs/view/3", "date": "2026-10-16", "applicants": None, "applicantsText": "Be among the first 25 applicants"})
        self.assertIn("Be among the first 25 applicants", early["signals"])


class Inputs(unittest.TestCase):
    def test_reads_detail_objects_search_outputs_and_seen_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "d.json").write_text(json.dumps(ct()), encoding="utf-8")
            (tmp / "s.json").write_text(json.dumps({"meta": {}, "results": [ct(id_="A" * 32)]}), encoding="utf-8")
            (tmp / "seen.json").write_text(
                json.dumps({"seen": {"k": {"title": "T", "company": "C", "url": CT.format("B" * 32), "posted_date": "2026-10-01"}}}),
                encoding="utf-8",
            )
            self.assertEqual(len(pf.load_postings(tmp / "d.json")), 1)
            self.assertEqual(pf.load_postings(tmp / "s.json")[0]["id"], "A" * 32)
            self.assertEqual(pf.load_postings(tmp / "seen.json")[0]["date"], "2026-10-01")

    def test_cli_prints_json_sorted_by_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.json"
            path.write_text(json.dumps([ct(id_="A" * 32, date="2026-08-01"), ct(id_="B" * 32, date="2026-10-17")]), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "pe_frescura.py"), str(path), "--json", "--today", "2026-10-18"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rows = json.loads(proc.stdout)["postings"]
            self.assertEqual([r["risk"] for r in rows], ["bajo", "alto"])

    def test_cli_text_output_names_window_and_advice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.json"
            path.write_text(json.dumps(ct(date="2026-10-17")), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(REPO / "tools" / "pe_frescura.py"), str(path), "--today", "2026-10-18"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("[BAJO ] fresca", proc.stdout)
            self.assertIn("postula ya", proc.stdout)


if __name__ == "__main__":
    unittest.main()

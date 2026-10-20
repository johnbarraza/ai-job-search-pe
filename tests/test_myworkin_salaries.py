"""Offline tests for tools/myworkin_salaries.py (MyWorkIn salary lookup, Peru fork).

Fixtures are trimmed from live pages fetched 2026-10-15; no test touches the network.
"""
import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("myworkin_salaries", REPO / "tools" / "myworkin_salaries.py")
mw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mw)

INDEX_HTML = """
<a data-spotlight="true" class="spotlight-card flex" href="/salaries/ferreycorp"><div class="flex items-start gap-3">
<div class="relative"><img alt="" srcSet="/_next/image?url=https%3A%2F%2Ffirebasestorage.googleapis.com%2Fv0%2Fb%2Fcore-commons.firebasestorage.app%2Fo%2Fcompany_logos%252Fferreycorp.jpg%3Falt%3Dmedia&amp;w=32&amp;q=75 32w"/></div>
<div class="min-w-0 flex-1"><h3 class="truncate font-display font-bold">Ferreycorp</h3>
<p class="truncate text-sm text-muted-foreground">Machinery</p></div></div>
<div class="mt-auto border-t border-border/60 pt-4"><p class="font-display font-bold">2<!-- --> salarios</p></div></a>
<a data-spotlight="true" class="spotlight-card flex" href="/salaries/rimac-seguros"><div>
<h3 class="truncate font-display font-bold">R&iacute;mac Seguros</h3>
<p class="truncate text-sm text-muted-foreground">Insurance</p>
<p class="font-display font-bold">30<!-- --> salarios</p></div></a>
<a href="/salaries">Volver a Salarios</a>
"""

COMPANY_HTML = """
<h1 class="font-display text-3xl">Credicorp</h1><p>27<!-- --> reportes · 21 puestos</p>
<table class="hidden w-full sm:table"><thead><tr><th>Puesto</th><th>Salario</th><th>Aportes</th></tr></thead>
<tbody class="divide-y divide-border/60">
<tr class="odd:bg-muted/30"><td class="w-full">Corporate Strategy Senior Analyst</td>
<td class="whitespace-nowrap">~ S/ 5,800 – S/ 6,200</td><td class="whitespace-nowrap">4</td></tr>
<tr class="odd:bg-muted/30"><td class="w-full">Practicante de Pricing</td>
<td class="whitespace-nowrap">~ S/ 1,350 – S/ 1,650</td><td class="whitespace-nowrap">1</td></tr>
<tr class="odd:bg-muted/30"><td class="w-full">Practicante de Pricing</td>
<td class="whitespace-nowrap">~ S/ 1,125 – S/ 1,375</td><td class="whitespace-nowrap">1</td></tr>
</tbody></table>
<p>Montos estimados en soles mensuales. USD ≈ S/ 3.75; anuales ÷ 12.</p>
"""


class ParseIndex(unittest.TestCase):
    def test_company_cards(self):
        companies = mw.parse_index(INDEX_HTML)
        self.assertEqual([c["slug"] for c in companies], ["ferreycorp", "rimac-seguros"])
        self.assertEqual(companies[1]["name"], "Rímac Seguros")
        self.assertEqual(companies[1]["sector"], "Insurance")
        self.assertEqual(companies[0]["reports"], 2)
        self.assertEqual(
            companies[0]["logo"],
            "https://firebasestorage.googleapis.com/v0/b/core-commons.firebasestorage.app/o/company_logos%2Fferreycorp.jpg?alt=media",
        )
        self.assertIsNone(companies[1]["logo"])

    def test_links_without_a_card_heading_are_skipped(self):
        self.assertEqual(mw.parse_index('<a href="/salaries/x">Ver</a>'), [])


class ParseCompany(unittest.TestCase):
    def test_rows_amounts_and_totals(self):
        parsed = mw.parse_company(COMPANY_HTML)
        self.assertEqual(parsed["name"], "Credicorp")
        self.assertEqual(parsed["reports"], 27)
        first = parsed["roles"][0]
        self.assertEqual(first["role"], "Corporate Strategy Senior Analyst")
        self.assertEqual((first["min"], first["max"], first["reports"]), (5800, 6200, 4))
        self.assertEqual(first["salary_text"], "S/ 5,800 – S/ 6,200")

    def test_no_table_yields_no_roles(self):
        self.assertEqual(mw.parse_company("<h1>X</h1>")["roles"], [])


class SalaryEntry(unittest.TestCase):
    def test_shape_matches_salary_lookup(self):
        entry = mw.to_salary_entry("credicorp", mw.parse_company(COMPANY_HTML))
        self.assertEqual(entry["company"], "Credicorp")
        cats = entry["categories"]
        self.assertEqual(cats["Corporate Strategy Senior Analyst"], {"count": 4, "index": "S/ 5,800 – 6,200"})
        # Duplicate role titles stay distinct rows instead of overwriting each other.
        self.assertIn("Practicante de Pricing (2)", cats)
        self.assertEqual(entry["source_url"], "https://www.myworkin.ai/salaries/credicorp")

    def test_written_file_passes_salary_lookup_validation(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "salary_data.json"
            mw.merge(out, mw.to_salary_entry("credicorp", mw.parse_company(COMPANY_HTML)))
            data = json.loads(out.read_text(encoding="utf-8"))
            errors, _ = mw.salary_lookup.collect_validation_issues(data)
            self.assertEqual(errors, [])
            self.assertEqual(mw.salary_lookup.search_company(data, "credicorp")[0]["company"], "Credicorp")

    def test_merge_replaces_the_same_company(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "salary_data.json"
            entry = mw.to_salary_entry("credicorp", mw.parse_company(COMPANY_HTML))
            mw.merge(out, entry)
            mw.merge(out, entry)
            self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["companies"]), 1)

    def test_merge_refuses_a_file_from_another_source(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "salary_data.json"
            out.write_text(json.dumps({"metadata": {"source": "Union stats 2025"}, "companies": []}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                mw.merge(out, mw.to_salary_entry("credicorp", mw.parse_company(COMPANY_HTML)))


class Matching(unittest.TestCase):
    COMPANIES = [
        {"slug": "pacifico-seguros", "name": "Pacífico Seguros", "reports": 9},
        {"slug": "pacifico-eps", "name": "Pacífico EPS", "reports": 4},
        {"slug": "rimac-seguros", "name": "Rímac Seguros", "reports": 30},
        {"slug": "ripley", "name": "Ripley", "reports": 3},
        {"slug": "banco-ripley", "name": "Banco Ripley", "reports": 2},
    ]

    def test_accent_insensitive(self):
        self.assertEqual(mw.best_matches(self.COMPANIES, "Rimac Seguros")[0][1]["slug"], "rimac-seguros")

    def test_exact_name_beats_a_longer_one(self):
        top = mw.best_matches(self.COMPANIES, "Ripley")
        self.assertEqual((top[0][0], top[0][1]["slug"]), (100, "ripley"))

    def test_close_scores_are_reported_as_ambiguous(self):
        with mock.patch.object(mw, "load_index", return_value=self.COMPANIES), \
                mock.patch("sys.stderr") as err:
            code = mw.main(["Pacífico", "--no-save"])
        self.assertEqual(code, 3)
        printed = "".join(call.args[0] for call in err.write.call_args_list)
        self.assertIn("pacifico-seguros", printed)
        self.assertIn("pacifico-eps", printed)


class Robots(unittest.TestCase):
    def test_disallowed_path_is_refused(self):
        robots = "User-Agent: *\nAllow: /\nDisallow: /salaries\n"
        with mock.patch.object(mw, "http_get", return_value=robots):
            with self.assertRaises(mw.FetchError):
                mw.check_robots("/salaries/credicorp")

    def test_current_policy_allows_salaries(self):
        robots = "User-Agent: *\nAllow: /\nDisallow: /jobs\nDisallow: /api\n"
        with mock.patch.object(mw, "http_get", return_value=robots):
            mw.check_robots("/salaries/credicorp")  # no exception

    def test_html_soft_200_is_not_a_policy(self):
        with mock.patch.object(mw, "http_get", return_value="<html>oops</html>"):
            with self.assertRaises(mw.FetchError):
                mw.check_robots("/salaries/credicorp")


if __name__ == "__main__":
    unittest.main()

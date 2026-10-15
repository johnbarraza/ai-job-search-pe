"""Tests for tools/pe_sueldo.py (Peruvian pay calculator, Peru fork).

Expected values are worked by hand from the 2026 parameters (UIT S/ 5,500, RMV
S/ 1,230, AFP 10% + 1.37% + flow commission) so a parameter or formula change that
moves them is caught.
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("pe_sueldo", REPO / "tools" / "pe_sueldo.py")
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)


class IncomeTax(unittest.TestCase):
    def test_below_seven_uit_pays_nothing(self):
        self.assertEqual(ps.impuesto_trabajo(38_500), 0)

    def test_first_bracket(self):
        # 56,720 - 38,500 = 18,220 at 8%
        self.assertAlmostEqual(ps.impuesto_trabajo(56_720), 1_457.6)

    def test_brackets_are_progressive(self):
        # renta neta 120,000: 27,500*8% + 82,500*14% + 10,000*17%
        self.assertAlmostEqual(ps.impuesto_trabajo(158_500), 2_200 + 11_550 + 1_700)

    def test_additional_deduction_is_capped_at_three_uit(self):
        self.assertAlmostEqual(ps.impuesto_trabajo(80_000, deduccion_adicional=99_999),
                               ps.impuesto_trabajo(80_000, deduccion_adicional=16_500))

    def test_cuarta_gets_twenty_percent_first(self):
        # 60,000 RxH: 60,000 - 12,000 - 38,500 = 9,500 at 8%
        self.assertAlmostEqual(ps.impuesto_trabajo(0, 60_000), 760)


class Planilla(unittest.TestCase):
    def test_general_regime_4000(self):
        r = ps.calcular(4000, "general", pension="integra")
        self.assertAlmostEqual(r["bruto_anual"], 56_720)          # 14 sueldos + 2 x 9%
        self.assertAlmostEqual(r["pension_mensual"], 4000 * (0.10 + 0.0155 + 0.0137))
        self.assertAlmostEqual(r["cts_anual"], 4000 + 4000 / 6)
        self.assertAlmostEqual(r["impuesto_anual"], 1_457.6)

    def test_small_company_pays_half_extras(self):
        r = ps.calcular(4000, "pequena")
        self.assertAlmostEqual(r["gratificacion_julio_y_diciembre"], 2000)
        self.assertAlmostEqual(r["cts_anual"], (4000 + 2000 / 6) * 0.5)  # 15 remuneraciones diarias

    def test_microempresa_pays_no_extras(self):
        r = ps.calcular(4000, "micro")
        self.assertEqual(r["bruto_anual"], 48_000)
        self.assertEqual(r["cts_anual"], 0)

    def test_onp_is_thirteen_percent(self):
        self.assertAlmostEqual(ps.calcular(4000, pension="onp")["pension_mensual"], 520)

    def test_afp_insurance_capped_at_rma(self):
        high = ps.pension_mensual(20_000, "prima")
        self.assertAlmostEqual(high, 20_000 * (0.10 + 0.016) + 12_672.65 * 0.0137)

    def test_mixed_commission_drops_the_flow_fee(self):
        self.assertAlmostEqual(ps.pension_mensual(4000, "integra-mixta"), 4000 * (0.10 + 0.0137))

    def test_family_allowance_is_ten_percent_of_rmv(self):
        r = ps.calcular(4000, asignacion_familiar=True)
        self.assertAlmostEqual(r["remuneracion_computable"], 4123)

    def test_below_rmv_is_flagged(self):
        self.assertTrue(any("RMV" in n for n in ps.calcular(1000)["notas"]))


class Honorarios(unittest.TestCase):
    def test_retention_and_refund(self):
        r = ps.calcular(4000, "rxh")
        self.assertAlmostEqual(r["retencion_mensual"], 320)
        self.assertEqual(r["impuesto_anual"], 0)               # 38,400 net after 20% < 7 UIT
        self.assertAlmostEqual(r["saldo_declaracion_anual"], -3_840)

    def test_no_retention_at_or_below_1500(self):
        self.assertEqual(ps.calcular(1500, "rxh")["retencion_mensual"], 0)


class Practicas(unittest.TestCase):
    def test_rmv_subvencion_plus_half_every_six_months(self):
        r = ps.calcular(1230, "practicas")
        self.assertAlmostEqual(r["bruto_anual"], 13 * 1230)
        self.assertFalse(any("menor a la RMV" in n for n in r["notas"]))

    def test_below_rmv_explains_the_proportional_rule(self):
        self.assertTrue(any("menor a la RMV" in n for n in ps.calcular(1000, "practicas")["notas"]))


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(REPO / "tools" / "pe_sueldo.py"), *args],
                              capture_output=True, env={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0",
                                                        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})

    def test_comparison_json_excludes_practicas(self):
        proc = self.run_cli("4000", "--comparar", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        regimes = [r["regimen"] for r in json.loads(proc.stdout.decode("utf-8"))]
        self.assertEqual(regimes, ["general", "pequena", "micro", "rxh"])

    def test_text_output_is_utf8_on_a_legacy_console(self):
        proc = self.run_cli("4000", "--regimen", "pequena")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("pequeña empresa", proc.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

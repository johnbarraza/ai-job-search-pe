#!/usr/bin/env python3
"""Peruvian pay calculator: what a monthly offer is worth per year and in hand.

A Peruvian offer quoted as "S/ 4,000" means very different things depending on the
contract: planilla in the general regime pays 14 sueldos plus a 9% bonus on each
gratificación plus CTS; a small company (REMYPE) pays half of those extras; a
microempresa pays none; a recibo por honorarios pays 12 receipts with no benefits; a
prácticas convenio pays a subvención plus half a subvención every six months. This tool
puts them side by side so /apply's fit evaluation and the user's negotiation compare
like with like.

Usage:
    python tools/pe_sueldo.py 4000                         # planilla, régimen general
    python tools/pe_sueldo.py 4000 --regimen rxh            # recibo por honorarios
    python tools/pe_sueldo.py 1300 --regimen practicas
    python tools/pe_sueldo.py 4000 --comparar               # every regime side by side
    python tools/pe_sueldo.py 4000 --pension onp --asignacion-familiar
    python tools/pe_sueldo.py 4000 --json

Figures are an estimate for a full calendar year in one job, using the parameters in
PARAMS below (verified 2026-10-15; update them when the UIT, RMV or AFP commissions
change). Monthly 5ta-categoría withholding is shown as annual tax / 12; the employer's
actual month-by-month schedule differs but adds up to the same annual amount.
"""

import argparse
import json
import sys

# ---------------------------------------------------------------------------
# Parameters (Peru, verified 2026-10-15). Sources in 10-peru-market.md.
# ---------------------------------------------------------------------------
PARAMS = {
    "year": 2026,
    # D.S. 015-2026-TR: RMV S/ 1,130 -> S/ 1,230 from 2026-10-01; a further S/ 70
    # (to S/ 1,300) needs another decreto supremo in the first half of 2027.
    "rmv": 1230,
    # D.S. 301-2025-EF.
    "uit": 5500,
    # Impuesto a la renta del trabajo: tramos over renta neta, in UIT.
    "tax_brackets_uit": [(5, 0.08), (20, 0.14), (35, 0.17), (45, 0.20), (None, 0.30)],
    "deduccion_uit": 7,            # fixed deduction on 4ta + 5ta
    "deduccion_adicional_max_uit": 3,  # sustained, bank-paid expenses (alquiler, médicos, …)
    "cuarta_deduccion_pct": 0.20,  # 4ta: presumed 20% deduction, capped at 24 UIT
    "cuarta_deduccion_tope_uit": 24,
    "rxh_retencion_pct": 0.08,     # withheld on receipts above S/ 1,500
    "rxh_retencion_umbral": 1500,
    "rxh_suspension_tope": 48125,  # 2026 annual ceiling to request suspension (8.75 UIT)
    # SPP (SBS tables, 2026): 10% fund + 1.37% insurance (on pay up to the RMA) + flow commission.
    "afp_aporte": 0.10,
    "afp_prima": 0.0137,
    "afp_rma": 12672.65,
    "afp_comision_flujo": {"habitat": 0.0147, "integra": 0.0155, "prima": 0.0160, "profuturo": 0.0169},
    "onp": 0.13,
    "essalud": 0.09,               # employer contribution, not a deduction
    "bonificacion_extraordinaria": 0.09,  # Ley 30334: 9% of each gratificación (6.75% with EPS)
}

REGIMENES = {
    "general": "Planilla - régimen general",
    "pequena": "Planilla - pequeña empresa (REMYPE)",
    "micro": "Planilla - microempresa (REMYPE)",
    "rxh": "Recibo por honorarios (4ta categoría)",
    "practicas": "Convenio de prácticas (Ley 28518)",
}


def impuesto_trabajo(renta_bruta_quinta, renta_bruta_cuarta=0.0, deduccion_adicional=0.0, p=PARAMS):
    """Annual income tax on rentas del trabajo (4ta + 5ta), SUNAT method."""
    uit = p["uit"]
    cuarta_neta = renta_bruta_cuarta - min(renta_bruta_cuarta * p["cuarta_deduccion_pct"],
                                           p["cuarta_deduccion_tope_uit"] * uit)
    adicional = min(max(deduccion_adicional, 0.0), p["deduccion_adicional_max_uit"] * uit)
    neta = max(0.0, cuarta_neta + renta_bruta_quinta - p["deduccion_uit"] * uit - adicional)
    tax, lower = 0.0, 0.0
    for top_uit, rate in p["tax_brackets_uit"]:
        upper = float("inf") if top_uit is None else top_uit * uit
        if neta > lower:
            tax += (min(neta, upper) - lower) * rate
        lower = upper
    return tax


def pension_mensual(remuneracion, pension, p=PARAMS):
    if pension == "onp":
        return remuneracion * p["onp"]
    if pension == "ninguna":
        return 0.0
    afp, _, mixta = pension.partition("-")
    flujo = 0.0 if mixta == "mixta" else p["afp_comision_flujo"][afp]
    return remuneracion * (p["afp_aporte"] + flujo) + min(remuneracion, p["afp_rma"]) * p["afp_prima"]


def calcular(monto, regimen="general", pension="integra", asignacion_familiar=False,
             deduccion_adicional=0.0, p=PARAMS):
    """Annual and monthly figures for one offer. `monto` is the monthly amount quoted."""
    r = {"regimen": regimen, "regimen_nombre": REGIMENES[regimen], "monto_mensual": monto}
    notes = []

    if regimen in ("general", "pequena", "micro"):
        asig = 0.10 * p["rmv"] if asignacion_familiar and regimen != "micro" else 0.0
        rem = monto + asig
        factor = {"general": 1.0, "pequena": 0.5, "micro": 0.0}[regimen]
        grati = rem * factor                     # each of July and December
        bono = grati * p["bonificacion_extraordinaria"]
        cts = (rem + grati / 6) * factor         # per year, deposited May / November
        bruto_anual = 12 * rem + 2 * grati + 2 * bono
        pen = pension_mensual(rem, pension, p)
        tax = impuesto_trabajo(bruto_anual, 0.0, deduccion_adicional, p)
        neto_anual = bruto_anual - 12 * pen - tax
        r.update({
            "remuneracion_computable": rem,
            "gratificacion_julio_y_diciembre": grati,
            "bonificacion_extraordinaria_c_u": bono,
            "cts_anual": cts,
            "bruto_anual": bruto_anual,
            "pension_mensual": pen,
            "impuesto_anual": tax,
            "neto_mes_normal": rem - pen - tax / 12,
            "neto_julio_diciembre": rem - pen - tax / 12 + grati + bono,
            "neto_anual": neto_anual,
            "valor_anual_con_cts": neto_anual + cts,
            "costo_empleador_anual": bruto_anual + cts + 12 * rem * p["essalud"],
        })
        if monto < p["rmv"]:
            notes.append(f"Por debajo de la RMV (S/ {p['rmv']:,}) para jornada completa.")
        if regimen == "micro":
            notes.append("Microempresa: sin gratificaciones ni CTS; 15 días de vacaciones.")
        if regimen == "pequena":
            notes.append("Pequeña empresa: media gratificación, CTS de 15 remuneraciones diarias, 15 días de vacaciones.")
        if regimen in ("pequena", "micro"):
            notes.append("Solo aplica si la empresa está inscrita en el REMYPE; si no, corresponde el régimen general.")
        notes.append(f"Pensión: {pension.upper()}." if pension == "onp" else f"Pensión: AFP {pension}.")

    elif regimen == "rxh":
        bruto_anual = 12 * monto
        retencion = monto * p["rxh_retencion_pct"] if monto > p["rxh_retencion_umbral"] else 0.0
        tax = impuesto_trabajo(0.0, bruto_anual, deduccion_adicional, p)
        r.update({
            "bruto_anual": bruto_anual,
            "retencion_mensual": retencion,
            "neto_mes_con_retencion": monto - retencion,
            "impuesto_anual": tax,
            "saldo_declaracion_anual": tax - 12 * retencion,
            "neto_anual": bruto_anual - tax,
            "valor_anual_con_cts": bruto_anual - tax,
        })
        notes.append("Sin gratificaciones, CTS, vacaciones pagadas ni EsSalud a cargo del contratante.")
        if bruto_anual <= p["rxh_suspension_tope"]:
            notes.append(f"Ingreso anual <= S/ {p['rxh_suspension_tope']:,}: puedes pedir suspensión de "
                         "retenciones (Formulario 1609, SUNAT).")
        if retencion and tax < 12 * retencion:
            notes.append("La retención del 8% excede el impuesto anual: SUNAT devuelve la diferencia.")
        notes.append("No se descuenta pensión: verifica la obligación vigente para independientes.")
        notes.append("Si el trabajo es subordinado (horario, jefe, exclusividad), es una relación laboral encubierta.")

    elif regimen == "practicas":
        adicional = monto                        # half a subvención per 6 continuous months = one per year
        bruto_anual = 12 * monto + adicional
        r.update({
            "subvencion_adicional_anual": adicional,
            "bruto_anual": bruto_anual,
            "neto_mes_normal": monto,
            "neto_anual": bruto_anual,
            "valor_anual_con_cts": bruto_anual,
        })
        if monto < p["rmv"]:
            notes.append(f"Subvención menor a la RMV (S/ {p['rmv']:,}): solo es legal si la jornada es menor "
                         "a la máxima (6 h/día o 30 h/semana preprofesional; 8 h/día o 48 h/semana profesional), "
                         "en proporción.")
        notes.append("Media subvención adicional cada 6 meses continuos; 15 días de descanso subvencionado si "
                     "el convenio supera 12 meses.")
        notes.append("Seguro a cargo de la empresa, sin descuento: lo más común es un seguro FOLA (privado, "
                     "red de clínicas de la aseguradora); algunas empresas usan EsSalud. Cobertura mínima: "
                     "14 subvenciones por enfermedad y 30 por accidente. Pregunta cuál te dan.")
        notes.append("Sin aporte pensionario obligatorio (afiliación facultativa).")

    r["notas"] = notes
    return r


def fmt(x):
    return f"S/ {x:,.0f}"


def render_one(r):
    rows = [(k, v) for k, v in r.items() if isinstance(v, float) or (isinstance(v, int) and k != "regimen")]
    labels = {
        "monto_mensual": "Monto mensual ofrecido",
        "remuneracion_computable": "Remuneración computable",
        "gratificacion_julio_y_diciembre": "Gratificación (julio y dic., c/u)",
        "bonificacion_extraordinaria_c_u": "Bonificación 9% (c/u)",
        "cts_anual": "CTS anual (depósito)",
        "bruto_anual": "Bruto anual",
        "pension_mensual": "Pensión mensual",
        "impuesto_anual": "Impuesto a la renta anual",
        "retencion_mensual": "Retención 8% por recibo",
        "neto_mes_con_retencion": "Neto mensual (tras retención)",
        "saldo_declaracion_anual": "Saldo en declaración anual (+pagar / -devolución)",
        "subvencion_adicional_anual": "Subvención adicional anual",
        "neto_mes_normal": "Neto mes normal",
        "neto_julio_diciembre": "Neto julio / diciembre",
        "neto_anual": "Neto anual (sin CTS)",
        "valor_anual_con_cts": "Valor anual (neto + CTS)",
        "costo_empleador_anual": "Costo anual para el empleador",
    }
    out = [f"{r['regimen_nombre']}  —  {fmt(r['monto_mensual'])} mensuales"]
    for k, v in rows:
        out.append(f"  {labels.get(k, k):<50} {fmt(v):>12}")
    for n in r["notas"]:
        out.append(f"  * {n}")
    return "\n".join(out)


def render_comparison(results):
    out = [f"Comparación para {fmt(results[0]['monto_mensual'])} mensuales ({PARAMS['year']}, RMV S/ {PARAMS['rmv']:,}, UIT S/ {PARAMS['uit']:,})",
           f"  {'Régimen':<40} {'Bruto anual':>12} {'Neto anual':>12} {'+ CTS':>12} {'Neto/mes prom.':>15}"]
    for r in results:
        out.append(f"  {r['regimen_nombre']:<40} {fmt(r['bruto_anual']):>12} {fmt(r['neto_anual']):>12} "
                   f"{fmt(r['valor_anual_con_cts']):>12} {fmt(r['valor_anual_con_cts'] / 12):>15}")
    out.append("  'Neto/mes prom.' = (neto anual + CTS) / 12: lo que la oferta vale de verdad por mes.")
    out.append("  Ojo: en planilla la pensión descontada va a TU fondo AFP/ONP y tienes EsSalud; por recibo no hay")
    out.append("  EsSalud, vacaciones pagadas ni fondo de pensión, así que un neto parecido no equivale a lo mismo.")
    return "\n".join(out)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent on a StringIO under test
        if reconfigure:
            reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("monto", type=float, help="monto mensual ofrecido en soles (sueldo, recibo o subvención)")
    ap.add_argument("--regimen", choices=list(REGIMENES), default="general")
    ap.add_argument("--pension", default="integra",
                    choices=["onp", "habitat", "integra", "prima", "profuturo",
                             "habitat-mixta", "integra-mixta", "prima-mixta", "profuturo-mixta"],
                    help="ONP, or AFP name (append -mixta for the balance-based commission)")
    ap.add_argument("--asignacion-familiar", action="store_true", help="tiene hijos menores: +10%% de la RMV")
    ap.add_argument("--deduccion-adicional", type=float, default=0.0,
                    help="gastos deducibles sustentados del año (alquiler, médicos…), tope 3 UIT")
    ap.add_argument("--comparar", action="store_true", help="mismo monto en planilla general, pequeña, micro y RxH")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.monto <= 0:
        ap.error("monto must be positive")

    kwargs = dict(pension=args.pension, asignacion_familiar=args.asignacion_familiar,
                  deduccion_adicional=args.deduccion_adicional)
    if args.comparar:
        # Prácticas are left out: a convenio is not an alternative contract for the same job.
        results = [calcular(args.monto, reg, **kwargs) for reg in REGIMENES if reg != "practicas"]
        print(json.dumps(results, ensure_ascii=False, indent=2) if args.json else render_comparison(results))
    else:
        r = calcular(args.monto, args.regimen, **kwargs)
        print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else render_one(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())

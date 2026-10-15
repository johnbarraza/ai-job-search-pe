// Shared vocabulary of the Peru portal CLIs: work mode (modality) and position level.
//
// This file is copied verbatim into every Peru portal CLI (computrabajo-search,
// bumeran-search, getonboard-search, linkedin-search, jev-search) so each skill stays a
// self-contained folder. tests/test_peru_vocab_sync.py fails when the copies differ:
// edit one copy, then copy it over the others.

export type Modality = "presencial" | "híbrido" | "remoto" | "no declarado"

export const MODALITIES: readonly Modality[] = ["presencial", "híbrido", "remoto", "no declarado"]

export type Level =
  | "práctica preprofesional"
  | "práctica profesional"
  | "práctica"
  | "pasantía"
  | "programa de extensión"
  | "trainee"
  | "asistente de investigación"
  | "asistente"
  | "analista"
  | "asociado"
  | "junior"
  | "semi senior"
  | "senior"
  | "jefatura"
  | "no declarado"

export const LEVELS: readonly Level[] = [
  "práctica preprofesional",
  "práctica profesional",
  "práctica",
  "pasantía",
  "programa de extensión",
  "trainee",
  "asistente de investigación",
  "asistente",
  "analista",
  "asociado",
  "junior",
  "semi senior",
  "senior",
  "jefatura",
  "no declarado",
]

/** Lowercase, strip accents, collapse whitespace: "Práctica  Pre-Profesional" -> "practica pre-profesional". */
export function fold(text: string | null | undefined): string {
  return (text ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
}

/**
 * Work mode from free text (a portal's work-mode label or a posting phrase). Anything that
 * names no mode is "no declarado", never a guess.
 */
export function normalizeModality(text: string | null | undefined): Modality {
  const t = fold(text)
  if (!t) return "no declarado"
  if (/hibrid|hybrid|presencial y remoto|remoto y presencial|semi-?presencial|mixt/.test(t)) return "híbrido"
  if (/remot|teletrabajo|home ?office|trabajo a distancia|work from home|100% virtual|\bvirtual\b/.test(t)) return "remoto"
  if (/presencial|on-?site|en oficina/.test(t)) return "presencial"
  return "no declarado"
}

// Ordered rules: the first match wins. Internship and programme types come first because
// they decide eligibility for a student; then research assistantships; then explicit
// seniority (a "Senior Analyst" is a senior role, not an analyst role for a new graduate);
// then the role words.
const LEVEL_RULES: Array<[RegExp, Level]> = [
  [/pre-? ?profesional/, "práctica preprofesional"],
  [/practicantes? profesional|practicas? profesional/, "práctica profesional"],
  [/\bpracticantes?\b|\bpracticas?\b|\bintern(ship)?s?\b|summer intern/, "práctica"],
  [/\bpasant(e|es|ia|ias)\b/, "pasantía"],
  [/programa de extension|curso de extension|\bpeu\b|programa de especializacion|curso de verano/, "programa de extensión"],
  [/\btrainee\b|graduate program|programa de (jovenes )?talentos?|jovenes profesionales/, "trainee"],
  [/asistente de investigacion|research assistant|investigador(a)? (junior|asistente)/, "asistente de investigación"],
  [/\b(jefe|jefa|gerente|subgerente|coordinador|coordinadora|supervisor|supervisora|head|lead|lider|manager|director|directora|encargado|encargada)\b/, "jefatura"],
  [/semi[- ]?senior|\bssr\b|semi sr/, "semi senior"],
  [/\bsenior\b|\bsr\b\.?/, "senior"],
  [/\bjunior\b|\bjr\b\.?/, "junior"],
  [/\basistente\b|\bauxiliar\b|\bassistant\b/, "asistente"],
  [/\basociad[oa]s?\b|\bassociate\b/, "asociado"],
  [/\banalista\b|\banalyst\b/, "analista"],
]

// A portal's own seniority label, used only when the title says nothing.
const PORTAL_LEVEL_RULES: Array<[RegExp, Level]> = [
  [/trainee|pasante|practicante/, "trainee"],
  [/sin experiencia|junior|entry/, "junior"],
  [/semi/, "semi senior"],
  [/senior|expert|\bsr\b/, "senior"],
  [/jefe|supervisor|gerente|manager|lead|director/, "jefatura"],
]

/** Position level from the title, falling back to the portal's seniority label. */
export function classifyLevel(title: string | null | undefined, portalLevel?: string | null): Level {
  const t = fold(title)
  for (const [re, level] of LEVEL_RULES) if (re.test(t)) return level
  const p = fold(portalLevel)
  if (p) for (const [re, level] of PORTAL_LEVEL_RULES) if (re.test(p)) return level
  return "no declarado"
}

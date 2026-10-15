import { describe, expect, test } from "bun:test";
import { classifyLevel, normalizeModality, LEVELS, MODALITIES } from "../src/peru";

// Shared-vocabulary tests, identical in every Peru portal CLI (as is src/peru.ts).
describe("peru vocabulary: modality", () => {
  test("work-mode labels and phrases", () => {
    expect(normalizeModality("Presencial y remoto")).toBe("híbrido");
    expect(normalizeModality("Híbrido")).toBe("híbrido");
    expect(normalizeModality("hybrid")).toBe("híbrido");
    expect(normalizeModality("Remoto")).toBe("remoto");
    expect(normalizeModality("100% virtual")).toBe("remoto");
    expect(normalizeModality("Teletrabajo")).toBe("remoto");
    expect(normalizeModality("Presencial")).toBe("presencial");
    expect(normalizeModality("on-site")).toBe("presencial");
  });

  test("anything else is 'no declarado', never a guess", () => {
    expect(normalizeModality(null)).toBe("no declarado");
    expect(normalizeModality("")).toBe("no declarado");
    expect(normalizeModality("Tiempo completo")).toBe("no declarado");
    expect(MODALITIES).toContain("no declarado");
  });
});

describe("peru vocabulary: level", () => {
  const cases: Array<[string, string]> = [
    ["Practicante Preprofesional de Economía y/o Administración, Sector Banca", "práctica preprofesional"],
    ["Practicante Pre-Profesional de Finanzas", "práctica preprofesional"],
    ["Prácticas Pre Profesionales - Riesgos", "práctica preprofesional"],
    ["Practicante Profesional de Contabilidad", "práctica profesional"],
    ["Prácticas Profesionales en Estudios Económicos", "práctica profesional"],
    ["Practicante de Pricing", "práctica"],
    ["Summer Intern", "práctica"],
    ["Pasantía en Regulación", "pasantía"],
    ["Programa de Extensión Universitaria 2027", "programa de extensión"],
    ["Curso de Extensión de Finanzas Avanzadas", "programa de extensión"],
    ["Management Trainee", "trainee"],
    ["Asistente de Investigación - Macroeconomía", "asistente de investigación"],
    ["Research Assistant (Development Economics)", "asistente de investigación"],
    ["Jefe de Planeamiento Financiero", "jefatura"],
    ["Senior Manager, Strategy", "jefatura"],
    ["Analista de Datos Semi Senior", "semi senior"],
    ["Analista Senior de Riesgos", "senior"],
    ["Analista Sr. de Tesorería", "senior"],
    ["Analista Junior de Inteligencia Comercial", "junior"],
    ["Junior Associate", "junior"],
    ["Asistente Contable", "asistente"],
    ["Auxiliar de Tesorería", "asistente"],
    ["Asociado de Auditoría", "asociado"],
    ["Analista de Pricing", "analista"],
    ["Economista", "no declarado"],
  ];
  for (const [title, level] of cases) {
    test(`"${title}" -> ${level}`, () => {
      expect(classifyLevel(title)).toBe(level as never);
    });
  }

  test("the portal's seniority is a fallback only when the title says nothing", () => {
    expect(classifyLevel("Economista", "Trainee / Pasante")).toBe("trainee");
    expect(classifyLevel("Economista", "Sin Experiencia")).toBe("junior");
    expect(classifyLevel("Economista", "Semi Sr")).toBe("semi senior");
    expect(classifyLevel("Analista de Pricing", "Senior")).toBe("analista");
    expect(classifyLevel("Economista", null)).toBe("no declarado");
  });

  test("every rule's level is in the declared vocabulary", () => {
    for (const [title] of cases) expect(LEVELS).toContain(classifyLevel(title));
  });
});

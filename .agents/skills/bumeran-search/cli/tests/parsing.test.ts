import { describe, test, expect } from "bun:test";
import {
  slugify,
  buildResultUrl,
  normalizeDate,
  daysSince,
  normalizeId,
  cleanDescriptionHtml,
  mapSearchItem,
  mapAvisoDetail,
  type RawSearchItem,
  type RawAvisoDetail,
  locationFiltros,
  ageFiltro,
  unappliedFiltros,
  normalizeModality,
} from "../src/helpers";

describe("slugify", () => {
  test("lowercases and hyphenates spaces", () => {
    expect(slugify("React Developer")).toBe("react-developer");
  });

  test("strips accents", () => {
    expect(slugify("Programación")).toBe("programacion");
  });

  test("collapses punctuation/slashes and trims stray hyphens", () => {
    // Modeled on the real live title used to verify buildResultUrl below.
    expect(slugify("Desarrollador Full Stack (JAVA / React) Senior - Mix (Onsite - Remoto) - 1778")).toBe(
      "desarrollador-full-stack-java-react-senior-mix-onsite-remoto-1778",
    );
  });
});

describe("buildResultUrl", () => {
  test("reproduces Bumeran's real seoFriendlyUrl for a live-captured example", () => {
    // Captured live on the Argentine site (same Navent backend and slug rules): id 1118379127.
    // The real seoFriendlyUrl (from GET fichaAvisoNormalizada) is:
    // /empleos/desarrollador-full-stack-java-react-senior-mix-onsite-remoto-1778-aliantec-1118379127.html
    const url = buildResultUrl(
      "1118379127",
      "Desarrollador Full Stack (JAVA / React) Senior - Mix (Onsite - Remoto) - 1778",
      "Aliantec",
    );
    expect(url).toBe(
      "https://www.bumeran.com.pe/empleos/desarrollador-full-stack-java-react-senior-mix-onsite-remoto-1778-aliantec-1118379127.html",
    );
  });

  test("omits the company segment when company is null", () => {
    const url = buildResultUrl("123456", "QA Engineer", null);
    expect(url).toBe("https://www.bumeran.com.pe/empleos/qa-engineer-123456.html");
  });
});

describe("normalizeDate", () => {
  test("converts Bumeran's DD-MM-YYYY to ISO", () => {
    expect(normalizeDate("23-07-2026")).toBe("2026-07-23");
  });

  test("returns null for missing/unparseable input", () => {
    expect(normalizeDate(null)).toBeNull();
    expect(normalizeDate(undefined)).toBeNull();
    expect(normalizeDate("not-a-date")).toBeNull();
  });
});

describe("daysSince", () => {
  const now = new Date("2026-07-27T12:00:00Z");

  test("computes whole days between an ISO date and now", () => {
    expect(daysSince("2026-07-24", now)).toBe(3);
  });

  test("returns 0 for today", () => {
    expect(daysSince("2026-07-27", now)).toBe(0);
  });

  test("returns null for null/invalid input", () => {
    expect(daysSince(null, now)).toBeNull();
    expect(daysSince("not-a-date", now)).toBeNull();
  });
});

describe("normalizeId", () => {
  test("bare numeric id passes through", () => {
    expect(normalizeId("1118379127")).toBe("1118379127");
  });

  test("extracts the trailing id from a full job URL", () => {
    expect(
      normalizeId(
        "https://www.bumeran.com.pe/empleos/desarrollador-full-stack-java-react-senior-1118379127.html",
      ),
    ).toBe("1118379127");
  });

  test("extracts from a bare 'aviso-<id>' style input", () => {
    expect(normalizeId("aviso-1118379127")).toBe("1118379127");
  });

  test("rejects empty/short input", () => {
    expect(normalizeId("")).toBeNull();
    expect(normalizeId("42")).toBeNull();
  });
});

describe("cleanDescriptionHtml", () => {
  test("strips tags, decodes entities, keeps block breaks as newlines", () => {
    const html = "<p><strong>¿Qu&eacute; hace la compa&ntilde;&iacute;a?</strong></p><p>Somos una empresa &amp; consultor&iacute;a.</p>";
    const cleaned = cleanDescriptionHtml(html);
    expect(cleaned).toContain("¿Qué hace la compañía?");
    expect(cleaned).toContain("Somos una empresa & consultoría.");
    expect(cleaned).not.toMatch(/<[^>]+>/);
  });

  test("returns null for empty/missing input", () => {
    expect(cleanDescriptionHtml(null)).toBeNull();
    expect(cleanDescriptionHtml("")).toBeNull();
  });
});

describe("mapSearchItem", () => {
  test("maps a real-shaped searchV2 content item", () => {
    const raw: RawSearchItem = {
      id: 1118379127,
      titulo: "Desarrollador Full Stack (JAVA / React) Senior",
      empresa: "Aliantec",
      localizacion: "San Isidro, Lima",
      fechaPublicacion: "23-07-2026",
    };
    const card = mapSearchItem(raw);
    expect(card.id).toBe("1118379127");
    expect(card.title).toBe(raw.titulo);
    expect(card.company).toBe("Aliantec");
    expect(card.location).toBe("San Isidro, Lima");
    expect(card.date).toBe("2026-07-23");
    expect(card.companyUrl).toBeNull();
    expect(card.url).toContain("1118379127.html");
  });

  test("missing fields become null, never omitted", () => {
    const raw: RawSearchItem = {
      id: 42424242,
      titulo: "Some Role",
      empresa: null,
      localizacion: null,
      fechaPublicacion: null,
    };
    const card = mapSearchItem(raw);
    expect(card.company).toBeNull();
    expect(card.location).toBeNull();
    expect(card.date).toBeNull();
  });
});

describe("mapAvisoDetail", () => {
  test("maps a real-shaped fichaAvisoNormalizada aviso object", () => {
    const raw: RawAvisoDetail = {
      id: 1118379127,
      titulo: "Desarrollador Full Stack (JAVA / React) Senior",
      descripcion: "<p><strong>Hola</strong></p>",
      empresa: { denominacion: "Aliantec" },
      localizacion: { detalle: "San Isidro, Lima, Peru" },
      fechaPublicacion: "23-07-2026",
      tipoTrabajo: { nombre: "Full-time" },
      modalidadTrabajo: { nombre: "Híbrido" },
      nivelLaboral: { nombre: "Senior" },
      area: { nombre: "Tecnología, Sistemas y Telecomunicaciones" },
      subArea: { nombre: "Programación" },
      redireccionURL: null,
      seoFriendlyUrl: "/empleos/desarrollador-full-stack-java-react-senior-aliantec-1118379127.html",
    };
    const job = mapAvisoDetail(raw);
    expect(job.id).toBe("1118379127");
    expect(job.company).toBe("Aliantec");
    expect(job.location).toBe("San Isidro, Lima, Peru");
    expect(job.date).toBe("2026-07-23");
    expect(job.employmentType).toBe("Full-time");
    expect(job.workMode).toBe("Híbrido");
    expect(job.seniority).toBe("Senior");
    expect(job.category).toBe("Programación");
    expect(job.description).toContain("Hola");
    expect(job.url).toBe(
      "https://www.bumeran.com.pe/empleos/desarrollador-full-stack-java-react-senior-aliantec-1118379127.html",
    );
  });

  test("falls back to a constructed url when seoFriendlyUrl is missing", () => {
    const raw: RawAvisoDetail = {
      id: 999,
      titulo: "QA Engineer",
      descripcion: null,
      empresa: { denominacion: "Acme" },
    };
    const job = mapAvisoDetail(raw);
    expect(job.url).toBe("https://www.bumeran.com.pe/empleos/qa-engineer-acme-999.html");
    expect(job.applyUrl).toBeNull();
  });

  test("freshness fields: expiry, state, vacancies, contract type; later edit is an update", () => {
    // Field shapes as served live (October 2026) by fichaAvisoNormalizada.
    const job = mapAvisoDetail({
      id: 1118384615,
      titulo: "Asistente de Reclutamiento y Selección",
      descripcion: null,
      fechaPublicacion: "13-10-2026",
      fechaModificado: "16-10-2026 10:06:27",
      fechaFinalizacion: "11-01-2027",
      estado: "activo",
      cantidadVacantes: 1,
      tipoContratacion: { nombre: "Temporal" },
      empresa: { denominacion: "C.MEJIA CONTRATISTAS GENERALES S.A.C.", industria: "Construcción", rangoEmpleados: "Entre 51 y 150" },
      localizacion: { detalle: "Los Olivos, Lima, Peru", direccion: null },
    });
    expect(job.industry).toBe("Construcción");
    expect(job.companySize).toBe("Entre 51 y 150");
    expect(job.address).toBeNull();
    expect(job.date).toBe("2026-10-13");
    expect(job.updated).toBe("2026-10-16");
    expect(job.validThrough).toBe("2027-01-11");
    expect(job.status).toBe("activo");
    expect(job.vacancies).toBe(1);
    expect(job.contractType).toBe("Temporal");
  });

  test("an edit on the publication day is not an update; absent fields are null", () => {
    const job = mapAvisoDetail({
      id: 1,
      titulo: "Analista",
      descripcion: null,
      fechaPublicacion: "15-10-2026",
      fechaModificado: "15-10-2026 13:11:22",
    });
    expect(job.updated).toBeNull();
    expect(job.validThrough).toBeNull();
    expect(job.status).toBeNull();
    expect(job.vacancies).toBeNull();
    expect(job.contractType).toBeNull();
  });
});

describe("mapSearchItem: confidential postings", () => {
  test("company stays 'Confidencial' but the url omits the company segment", () => {
    // Live shape (October 2026): confidential postings carry empresa "Confidencial" and
    // Bumeran's own seoFriendlyUrl is /empleos/<title>-<id>.html with no company slug.
    const card = mapSearchItem({
      id: 1118483020,
      titulo: "Analista de Compras",
      empresa: "Confidencial",
      confidencial: true,
      localizacion: "San Juan De Lurigancho., Lima",
      fechaPublicacion: "15-10-2026",
    });
    expect(card.company).toBe("Confidencial");
    expect(card.url).toBe("https://www.bumeran.com.pe/empleos/analista-de-compras-1118483020.html");
  });
});

describe("locationFiltros", () => {
  test("regions map to provincia, with the Cusco/Cuzco alias", () => {
    expect(locationFiltros("Lima")).toEqual([{ id: "provincia", value: "peru|lima" }]);
    expect(locationFiltros("La Libertad")).toEqual([{ id: "provincia", value: "peru|la-libertad" }]);
    expect(locationFiltros("Cusco")).toEqual([{ id: "provincia", value: "peru|cuzco" }]);
  });

  test("Lima districts map to localidad, shorthands resolved", () => {
    expect(locationFiltros("San Isidro")).toEqual([{ id: "localidad", value: "peru|lima|san-isidro" }]);
    expect(locationFiltros("SJL")).toEqual([{ id: "localidad", value: "peru|lima|san-juan-de-lurigancho" }]);
  });

  test("districts with several Bumeran spellings send every variant", () => {
    const values = locationFiltros("Ate").map((f) => f.value);
    expect(values).toEqual(["peru|lima|ate", "peru|lima|ate-vitarte"]);
    expect(locationFiltros("Magdalena").map((f) => f.value)).toContain("peru|lima|magdalena-del-mar");
  });

  test("Callao resolves to its districts under provincia Lima", () => {
    const values = locationFiltros("Callao").map((f) => f.value);
    expect(values).toContain("peru|lima|callao");
    expect(values).toContain("peru|lima|ventanilla");
  });

  test("'<Region> en <City>' maps to a nested localidad", () => {
    expect(locationFiltros("Piura en Sullana")).toEqual([{ id: "localidad", value: "peru|piura|sullana" }]);
    expect(locationFiltros("Cusco en Wanchaq")).toEqual([{ id: "localidad", value: "peru|cuzco|wanchaq" }]);
  });
});

describe("ageFiltro", () => {
  test("picks the smallest bucket that still covers the window", () => {
    expect(ageFiltro(1)?.value).toBe("publicacion-hoy");
    expect(ageFiltro(7)?.value).toBe("publicacion-menor-a-7-dias");
    expect(ageFiltro(10)?.value).toBe("publicacion-menor-a-15-dias");
    expect(ageFiltro(14)?.value).toBe("publicacion-menor-a-15-dias");
    expect(ageFiltro(30)?.value).toBe("publicacion-menor-a-1-mes");
  });

  test("windows beyond a month get no server filter", () => {
    expect(ageFiltro(45)).toBeNull();
  });
});

describe("unappliedFiltros", () => {
  test("reports requested filtros missing from filtersApplied", () => {
    const requested = [
      { id: "provincia", value: "peru|lima" },
      { id: "nivel_laboral", value: "junior" },
    ];
    const applied = [{ idSemantico: "peru|lima" }, { value: "analista" }];
    expect(unappliedFiltros(requested, applied)).toEqual([{ id: "nivel_laboral", value: "junior" }]);
  });
});

describe("modality", () => {
  test("Bumeran's modalidadTrabajo maps to the shared vocabulary", () => {
    expect(normalizeModality("Presencial")).toBe("presencial");
    expect(normalizeModality("Híbrido")).toBe("híbrido");
    expect(normalizeModality("Remoto")).toBe("remoto");
    expect(normalizeModality(null)).toBe("no declarado");
  });

  test("search and detail items both carry it", () => {
    const card = mapSearchItem({
      id: 1, titulo: "Analista", empresa: "Acme", localizacion: "Lima, Lima",
      fechaPublicacion: "15-10-2026", modalidadTrabajo: "Híbrido",
    });
    expect(card.modality).toBe("híbrido");
    expect(card.level).toBe("analista");
    const job = mapAvisoDetail({
      id: 2, titulo: "Economista", descripcion: null, modalidadTrabajo: { nombre: "Remoto" },
      nivelLaboral: { nombre: "Trainee / Pasante" },
    });
    expect(job.modality).toBe("remoto");
    expect(job.level).toBe("trainee"); // title says nothing, so nivelLaboral decides
  });
});

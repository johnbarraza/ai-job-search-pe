import { afterEach, describe, expect, test } from "bun:test";
import { runSearch, type SearchOpts } from "../src/commands/search";

const originalFetch = globalThis.fetch;
const originalStdoutWrite = process.stdout.write;
const originalStderrWrite = process.stderr.write;

interface RawItem {
  id: number;
  titulo: string;
  empresa: string | null;
  confidencial?: boolean;
  localizacion: string | null;
  fechaPublicacion: string | null;
}

interface Captured {
  body: { filtros: Array<{ id: string; value: string }>; query: string } | null;
  url: string;
}

// Mock searchV2. `echo` controls which requested filtro values come back in
// filtersApplied (the API's own signal that a filter was recognized); by default every
// requested filtro is echoed, as the live API does for valid idSemanticos.
function mockApi(items: RawItem[], echo?: (value: string) => boolean): Captured {
  const captured: Captured = { body: null, url: "" };
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    captured.url = typeof url === "string" ? url : url instanceof URL ? url.href : url.url;
    captured.body = init?.body ? JSON.parse(String(init.body)) : null;
    const filtros = captured.body?.filtros ?? [];
    const applied = filtros
      .filter((f) => (echo ? echo(f.value) : true))
      .map((f) => ({ type: f.id, idSemantico: f.value }));
    const ok = filtros.length === 0 || applied.length > 0;
    return new Response(
      JSON.stringify({ total: ok ? items.length : 0, content: ok ? items : [], filtersApplied: applied }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as unknown as typeof fetch;
  return captured;
}

function captureStdout(): { get: () => string } {
  let out = "";
  process.stdout.write = ((chunk: string | Uint8Array) => {
    out += chunk.toString();
    return true;
  }) as typeof process.stdout.write;
  return { get: () => out };
}

function captureStderr(): { get: () => string } {
  let out = "";
  process.stderr.write = ((chunk: string | Uint8Array) => {
    out += chunk.toString();
    return true;
  }) as typeof process.stderr.write;
  return { get: () => out };
}

const base: SearchOpts = { jobage: 9999, page: 1, sort: "relevant", format: "json" };

afterEach(() => {
  globalThis.fetch = originalFetch;
  process.stdout.write = originalStdoutWrite;
  process.stderr.write = originalStderrWrite;
});

describe("runSearch: request shape", () => {
  test("region --location becomes a provincia filtro", async () => {
    const cap = mockApi([]);
    captureStdout();
    await runSearch({ ...base, query: "analista", location: "Arequipa" });
    expect(cap.body?.filtros).toEqual([{ id: "provincia", value: "peru|arequipa" }]);
    expect(cap.body?.query).toBe("analista");
  });

  test("district variants are all sent (the API ORs them)", async () => {
    const cap = mockApi([]);
    captureStdout();
    await runSearch({ ...base, location: "Surco" });
    const values = cap.body?.filtros.map((f) => f.value) ?? [];
    expect(values).toContain("peru|lima|santiago-de-surco");
    expect(values).toContain("peru|lima|surco");
    expect(cap.body?.filtros.every((f) => f.id === "localidad")).toBe(true);
  });

  test("--remote, --level, --jobage and --sort map to server-side parameters", async () => {
    const cap = mockApi([]);
    captureStdout();
    await runSearch({ ...base, remote: "hybrid", level: "junior", jobage: 10, sort: "recent" });
    expect(cap.body?.filtros).toEqual([
      { id: "modalidad_trabajo", value: "hibrido" },
      { id: "nivel_laboral", value: "junior" },
      { id: "dias_fecha_publicacion", value: "publicacion-menor-a-15-dias" },
    ]);
    expect(cap.url).toContain("sort=RECIENTES");
    expect(cap.url).toContain("page=0");
  });

  test("--page is 1-indexed on the CLI, 0-indexed on the API", async () => {
    const cap = mockApi([]);
    captureStdout();
    await runSearch({ ...base, query: "x", page: 3 });
    expect(cap.url).toContain("page=2");
  });
});

describe("runSearch: unrecognized filters are errors, not empty results", () => {
  test("a location the API does not echo exits 1 with LOCATION_NOT_FOUND", async () => {
    mockApi([], () => false);
    captureStdout();
    const stderr = captureStderr();
    const code = await runSearch({ ...base, query: "analista", location: "Narnia" });
    expect(code).toBe(1);
    expect(JSON.parse(stderr.get()).code).toBe("LOCATION_NOT_FOUND");
  });

  test("one recognized district variant out of several is enough", async () => {
    mockApi(
      [{ id: 7, titulo: "Analista", empresa: "Acme", localizacion: "Santiago de Surco, Lima", fechaPublicacion: "15-10-2026" }],
      (v) => v === "peru|lima|santiago-de-surco",
    );
    const stdout = captureStdout();
    const code = await runSearch({ ...base, location: "Surco" });
    expect(code).toBe(0);
    expect(JSON.parse(stdout.get()).results).toHaveLength(1);
  });
});

describe("runSearch: output", () => {
  test("--limit caps emitted results", async () => {
    mockApi([
      { id: 1, titulo: "A", empresa: "Acme", localizacion: "Lima, Lima", fechaPublicacion: "15-10-2026" },
      { id: 2, titulo: "B", empresa: "Acme", localizacion: "Lima, Lima", fechaPublicacion: "15-10-2026" },
    ]);
    const stdout = captureStdout();
    const code = await runSearch({ ...base, limit: 1 });
    expect(code).toBe(0);
    expect(JSON.parse(stdout.get()).results).toHaveLength(1);
  });

  test("--jobage trims to the exact window inside a wider server bucket", async () => {
    const now = new Date();
    const old = new Date(now.getTime() - 12 * 86400000);
    const fmt = (d: Date) =>
      `${String(d.getUTCDate()).padStart(2, "0")}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${d.getUTCFullYear()}`;
    mockApi([
      { id: 1, titulo: "Fresh", empresa: null, localizacion: null, fechaPublicacion: fmt(now) },
      { id: 2, titulo: "Twelve days", empresa: null, localizacion: null, fechaPublicacion: fmt(old) },
    ]);
    const stdout = captureStdout();
    const code = await runSearch({ ...base, jobage: 10 });
    expect(code).toBe(0);
    expect(JSON.parse(stdout.get()).results.map((r: { id: string }) => r.id)).toEqual(["1"]);
  });

  test("missing fields on a result item become null, not omitted", async () => {
    mockApi([{ id: 5, titulo: "Role", empresa: null, localizacion: null, fechaPublicacion: null }]);
    const stdout = captureStdout();
    await runSearch(base);
    const [result] = JSON.parse(stdout.get()).results;
    expect(result.company).toBeNull();
    expect(result.location).toBeNull();
    expect(result.date).toBeNull();
    expect(result.workMode).toBeNull();
    expect(result.url).toContain("5.html");
  });
});

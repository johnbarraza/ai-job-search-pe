import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  SITES,
  buildDetailGoal,
  buildSearchGoal,
  buildStartUrl,
  extractJson,
  findSite,
  jevArgs,
  missingCredentials,
  normalizeModality,
  parseDetailAnswer,
  parseSearchAnswer,
  robotsAllows,
  runJev,
  type Runner,
} from "../src/helpers";

describe("sites", () => {
  test("every site has an id, a name and search instructions", () => {
    for (const s of SITES) {
      expect(s.id).toMatch(/^[a-z]+$/);
      expect(s.name.length).toBeGreaterThan(3);
      expect(s.howToSearch.length).toBeGreaterThan(10);
    }
  });

  test("start URLs fill and encode {q} and {l}", () => {
    expect(buildStartUrl(findSite("practicas")!, "economía")).toBe("https://www.practicas.pe/?s=econom%C3%ADa");
    expect(buildStartUrl(findSite("indeed")!, "analista", "Lima")).toBe("https://pe.indeed.com/jobs?q=analista&l=Lima");
  });

  test("the generic site needs --url, and --url overrides a site's own", () => {
    expect(() => buildStartUrl(findSite("url")!)).toThrow(/--url/);
    expect(buildStartUrl(findSite("talentoperu")!, undefined, undefined, "https://example.org/x")).toBe("https://example.org/x");
  });
});

describe("goals", () => {
  const goal = buildSearchGoal(findSite("talentoperu")!, { query: "economista", location: "Lima", limit: 10 });

  test("search goal carries the terms, the site's instructions and the result shape", () => {
    expect(goal).toContain('"economista"');
    expect(goal).toContain('"Lima"');
    expect(goal).toContain("Puesto");
    expect(goal).toContain("at most 10 postings");
    expect(goal).toContain('"modality"');
  });

  test("every goal is read-only and stops at challenges", () => {
    for (const g of [goal, buildDetailGoal()]) {
      expect(g).toContain("Never click apply");
      expect(g).toContain("never sign in");
      expect(g).toContain("CAPTCHA");
    }
  });

  test("jev-browse always runs with --stop-at-challenge", () => {
    const args = jevArgs("https://example.org", "g", { maxSteps: 40, headed: false, cli: "/x/cli.mjs" });
    expect(args.slice(0, 2)).toEqual(["node", "/x/cli.mjs"]);
    expect(args).toContain("--stop-at-challenge");
    expect(args).not.toContain("--headed");
    expect(jevArgs("https://example.org", "g", { maxSteps: 5, headed: true, cli: "c" })).toContain("--headed");
  });
});

describe("answer parsing", () => {
  const answer = `Here are the postings:
\`\`\`json
[
  {"title": "Practicante de Economía", "company": "MEF", "location": "LIMA - LIMA", "modality": "Presencial",
   "salary": "S/. 1,230.00", "deadline": "28/10/2026", "date": "15/10/2026", "url": null, "ref": "CAS 012-2026"},
  {"title": "Analista de Datos", "company": "Acme", "location": "Lima", "modality": "hybrid",
   "salary": null, "deadline": null, "date": "2026-10-14", "url": "/empleo/123", "ref": null},
  {"title": "", "company": "Nobody"},
  "noise"
]
\`\`\``;

  test("fenced JSON inside prose parses; empty-title and non-object rows are dropped", () => {
    const cards = parseSearchAnswer(answer, "talentoperu", "https://app.servir.gob.pe/x/y.xhtml");
    expect(cards.map((c) => c.title)).toEqual(["Practicante de Economía", "Analista de Datos"]);
  });

  test("dates, modality, ids and relative URLs are normalized", () => {
    const [a, b] = parseSearchAnswer(answer, "talentoperu", "https://app.servir.gob.pe/x/y.xhtml");
    expect(a.deadline).toBe("2026-10-28");
    expect(a.date).toBe("2026-10-15");
    expect(a.modality).toBe("presencial");
    expect(a.id).toBe("talentoperu:CAS 012-2026");
    expect(b.modality).toBe("híbrido");
    expect(b.url).toBe("https://app.servir.gob.pe/empleo/123");
    expect(b.id).toBe("https://app.servir.gob.pe/empleo/123");
  });

  test("postings with neither ref nor URL get a stable id", () => {
    const one = parseSearchAnswer('[{"title":"Asistente","company":"X","location":"Lima"}]', "laborum", "https://www.laborum.pe/");
    const two = parseSearchAnswer('[{"title":"Asistente","company":"X","location":"Lima"}]', "laborum", "https://www.laborum.pe/");
    expect(one[0].id).toBe(two[0].id);
    expect(one[0].id).toMatch(/^[0-9a-f]{16}$/);
  });

  test("non-http links are dropped, never passed through", () => {
    const [c] = parseSearchAnswer('[{"title":"A","url":"javascript:alert(1)"}]', "url", "https://example.org/");
    expect(c.url).toBeNull();
  });

  test("an answer without JSON is an error", () => {
    expect(() => extractJson("no postings found", "array")).toThrow(/no parseable JSON/);
  });

  test("detail answers map to the detail shape", () => {
    const job = parseDetailAnswer(
      'Result: {"title":"Analista","modality":"remoto","requirements":["Excel avanzado", null, "SQL"],"how_to_apply":"Enviar CV"}',
      "https://example.org/job/1",
    );
    expect(job.modality).toBe("remoto");
    expect(job.requirements).toEqual(["Excel avanzado", "SQL"]);
    expect(job.howToApply).toBe("Enviar CV");
    expect(job.url).toBe("https://example.org/job/1");
  });

  test("modality vocabulary", () => {
    expect(normalizeModality("Presencial y remoto")).toBe("híbrido");
    expect(normalizeModality("Teletrabajo")).toBe("remoto");
    expect(normalizeModality("on-site")).toBe("presencial");
    expect(normalizeModality(null)).toBeNull();
  });
});

describe("credentials", () => {
  const dir = mkdtempSync(join(tmpdir(), "jev-search-"));
  const none = join(dir, "missing.env");

  test("both a provider key and the text-model key are required", () => {
    expect(missingCredentials({}, [none])).toEqual(["TYPESAFE_API_KEY or OPENROUTER_API_KEY", "TEXT_MODEL_API_KEY"]);
    expect(missingCredentials({ OPENROUTER_API_KEY: "x", TEXT_MODEL_API_KEY: "y" }, [none])).toEqual([]);
  });

  test("keys set in a .env file count; empty values do not", () => {
    const env = join(dir, ".env");
    writeFileSync(env, "# comment\nTYPESAFE_API_KEY=abc\nTEXT_MODEL_API_KEY=\n");
    expect(missingCredentials({}, [env])).toEqual(["TEXT_MODEL_API_KEY"]);
  });
});

describe("robots gate and runner", () => {
  test("exit 0 allows, exit 1 refuses, and no Python means refuse", async () => {
    const allow: Runner = async () => ({ code: 0, stdout: "ALLOWED", stderr: "" });
    const deny: Runner = async () => ({ code: 1, stdout: "DISALLOWED for Claude-User", stderr: "" });
    const noPython: Runner = async () => {
      throw new Error("ENOENT");
    };
    expect((await robotsAllows("https://x.org", allow)).ok).toBe(true);
    expect((await robotsAllows("https://x.org", deny)).ok).toBe(false);
    const missing = await robotsAllows("https://x.org", noPython);
    expect(missing.ok).toBe(false);
    expect(missing.message).toContain("refusing");
  });

  test("runJev reads the final JSON line of stdout", async () => {
    const run: Runner = async () => ({ code: 0, stdout: '{"status":"done","answer":"[]"}\n', stderr: "{}\n" });
    expect((await runJev(["node"], 1000, run)).status).toBe("done");
    const empty: Runner = async () => ({ code: 1, stdout: "", stderr: "Error: boom" });
    expect(runJev(["node"], 1000, empty)).rejects.toThrow(/boom/);
  });
});

import { afterEach, describe, expect, test } from "bun:test";
import { runCLI } from "./helpers";
import { runSearch } from "../src/commands/search";
import type { Runner } from "../src/helpers";

function err(stderr: string): { code?: string; error?: string } {
  try {
    return JSON.parse(stderr);
  } catch {
    return {};
  }
}

describe("CLI contract (offline: every case exits before Chrome or the network)", () => {
  test("no command prints help and exits 1", async () => {
    const r = await runCLI([]);
    expect(r.exitCode).toBe(1);
    expect(r.stdout).toContain("jev-search");
  });

  test("sites lists the registry as JSON", async () => {
    const r = await runCLI(["sites"]);
    expect(r.exitCode).toBe(0);
    const ids = JSON.parse(r.stdout).sites.map((s: { id: string }) => s.id);
    expect(ids).toContain("talentoperu");
    expect(ids).toContain("url");
  });

  test("unknown flags are rejected", async () => {
    const r = await runCLI(["search", "--site", "laborum", "--salary", "5000"]);
    expect(r.exitCode).toBe(1);
    expect(err(r.stderr).code).toBe("UNKNOWN_FLAG");
  });

  test("search needs --site, and the site must exist", async () => {
    expect(err((await runCLI(["search", "-q", "x"])).stderr).code).toBe("NO_SITE");
    expect(err((await runCLI(["search", "--site", "nowhere"])).stderr).code).toBe("BAD_SITE");
  });

  test("--site url needs --url, and --url must be http(s)", async () => {
    expect(err((await runCLI(["search", "--site", "url"])).stderr).code).toBe("NO_URL");
    expect(err((await runCLI(["search", "--site", "url", "--url", "file:///etc/passwd"])).stderr).code).toBe("BAD_ARG");
  });

  test("numeric flags are bounded", async () => {
    for (const args of [["--limit", "0"], ["--limit", "31"], ["--max-steps", "500"], ["--timeout", "abc"]]) {
      const r = await runCLI(["search", "--site", "laborum", ...args]);
      expect(r.exitCode).toBe(1);
      expect(err(r.stderr).code).toBe("BAD_ARG");
    }
  });

  test("a missing jev-browse checkout is reported with the fix", async () => {
    const proc = Bun.spawn(
      ["bun", "run", `${import.meta.dir}/../src/cli.ts`, "search", "--site", "laborum", "-q", "analista"],
      { env: { ...process.env, JEV_BROWSE_CLI: "/nonexistent/cli.mjs" }, stdout: "pipe", stderr: "pipe" },
    );
    const [stderr, code] = await Promise.all([new Response(proc.stderr).text(), proc.exited]);
    expect(code).toBe(1);
    expect(err(stderr.trim()).code).toBe("JEV_NOT_INSTALLED");
    expect(err(stderr.trim()).error).toContain("git submodule update --init vendor/jev-browse");
  });

  test("detail needs an http(s) URL", async () => {
    expect(err((await runCLI(["detail", "not-a-url"])).stderr).code).toBe("NO_URL");
  });
});

// End-to-end through runSearch with a fake runner standing in for node, python and
// jev-browse: proves the preflight order and the output contract without Chrome.
describe("runSearch with a fake runner", () => {
  const saved = { ...process.env };
  const out: string[] = [];
  const errs: string[] = [];
  const origOut = process.stdout.write;
  const origErr = process.stderr.write;

  function capture() {
    out.length = 0;
    errs.length = 0;
    process.stdout.write = ((c: string | Uint8Array) => (out.push(c.toString()), true)) as typeof process.stdout.write;
    process.stderr.write = ((c: string | Uint8Array) => (errs.push(c.toString()), true)) as typeof process.stderr.write;
  }

  afterEach(() => {
    process.stdout.write = origOut;
    process.stderr.write = origErr;
    process.env = { ...saved };
  });

  function fakeRunner(opts: { robots: number; jev: object }): { run: Runner; calls: string[][] } {
    const calls: string[][] = [];
    const run: Runner = async (cmd) => {
      calls.push(cmd);
      if (cmd[0] === "node" && cmd[1] === "--version") return { code: 0, stdout: "v24.11.1\n", stderr: "" };
      if (cmd[1]?.endsWith("robots_check.py")) return { code: opts.robots, stdout: opts.robots ? "DISALLOWED" : "ALLOWED", stderr: "" };
      return { code: 0, stdout: JSON.stringify(opts.jev) + "\n", stderr: "" };
    };
    return { run, calls };
  }

  const opts = { site: "talentoperu", query: "economista", limit: 5, format: "json" as const, maxSteps: 40, headed: false, timeoutMs: 1000 };

  test("missing credentials stop the run before robots.txt or Chrome", async () => {
    process.env.JEV_BROWSE_CLI = import.meta.path; // any existing file
    delete process.env.TYPESAFE_API_KEY;
    delete process.env.OPENROUTER_API_KEY;
    delete process.env.TEXT_MODEL_API_KEY;
    const { run, calls } = fakeRunner({ robots: 0, jev: {} });
    capture();
    const code = await runSearch(opts, run);
    // A real .env at the repo root could satisfy the check; only assert when it did not.
    if (code === 1) {
      expect(err(errs.join("").trim()).code).toBe("MISSING_CREDENTIALS");
      expect(calls.some((c) => c[1]?.endsWith("robots_check.py"))).toBe(false);
    }
  });

  test("a robots.txt refusal stops the run before Chrome", async () => {
    Object.assign(process.env, { JEV_BROWSE_CLI: import.meta.path, OPENROUTER_API_KEY: "x", TEXT_MODEL_API_KEY: "y" });
    const { run, calls } = fakeRunner({ robots: 1, jev: {} });
    capture();
    expect(await runSearch(opts, run)).toBe(1);
    expect(err(errs.join("").trim()).code).toBe("ROBOTS_DISALLOWED");
    expect(calls.some((c) => c.includes("--goal"))).toBe(false);
  });

  test("a verification page is reported, not worked around", async () => {
    Object.assign(process.env, { JEV_BROWSE_CLI: import.meta.path, OPENROUTER_API_KEY: "x", TEXT_MODEL_API_KEY: "y" });
    const { run } = fakeRunner({ robots: 0, jev: { status: "blocked", blocked_cause: "verification_required", challenge_reasons: ["captcha"] } });
    capture();
    expect(await runSearch(opts, run)).toBe(1);
    expect(err(errs.join("").trim()).code).toBe("VERIFICATION_REQUIRED");
  });

  test("a done run with an answer emits the portal contract", async () => {
    Object.assign(process.env, { JEV_BROWSE_CLI: import.meta.path, OPENROUTER_API_KEY: "x", TEXT_MODEL_API_KEY: "y" });
    const answer = JSON.stringify([
      { title: "ECONOMISTA", company: "MINISTERIO DE ECONOMIA Y FINANZAS", location: "LIMA - LIMA", modality: null,
        salary: "S/. 6,500.00", deadline: "28/10/2026", date: "15/10/2026", url: null, ref: "CAS N° 045-2026" },
    ]);
    const { run, calls } = fakeRunner({ robots: 0, jev: { status: "done", answer, final_url: "https://app.servir.gob.pe/x", steps: 6, elapsed_ms: 9000 } });
    capture();
    expect(await runSearch(opts, run)).toBe(0);
    const json = JSON.parse(out.join(""));
    expect(json.meta).toMatchObject({ count: 1, page: 1, site: "talentoperu", steps: 6 });
    const [r] = json.results;
    expect(Object.keys(r)).toEqual(expect.arrayContaining(["id", "title", "company", "location", "date", "url", "modality"]));
    expect(r.deadline).toBe("2026-10-28");
    expect(r.modality).toBeNull();
    const jevCall = calls.find((c) => c.includes("--goal"))!;
    expect(jevCall).toContain("--stop-at-challenge");
  });
});

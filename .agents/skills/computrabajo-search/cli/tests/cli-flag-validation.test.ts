import { describe, test, expect } from "bun:test";
import { runCLI } from "./helpers";

function parsedStderr(stderr: string): { error?: string; code?: string } {
  try {
    return JSON.parse(stderr);
  } catch {
    return {};
  }
}

describe("Computrabajo CLI flag validation", () => {
  describe("--jobage NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-q", "react", "--jobage", "foo"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/jobage/);
    });

    test("zero and fractions are rejected (whole numbers >= 1 only)", async () => {
      for (const bad of ["0", "0.5", "7days"]) {
        const result = await runCLI(["search", "-q", "react", "--jobage", bad]);
        expect(result.exitCode).toBe(1);
        expect(parsedStderr(result.stderr).code).toBe("BAD_ARG");
      }
    });
  });

  describe("--page NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-q", "react", "--page", "abc"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/page/);
    });
  });

  describe("--limit NaN validation", () => {
    test("non-numeric string exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-q", "react", "--limit", "xyz"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_ARG");
      expect(err.error).toMatch(/limit/);
    });
  });

  describe("search requires --query or --location", () => {
    test("bare search with neither exits 1 with NO_QUERY", async () => {
      const result = await runCLI(["search"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_QUERY");
    });

    test("--location alone (no --query) does not fail flag validation", async () => {
      const result = await runCLI(["search", "-l", "Lima", "--limit", "1"]);
      const err = parsedStderr(result.stderr);
      expect(err.code).not.toBe("NO_QUERY");
      expect(err.code).not.toBe("BAD_ARG");
    });
  });

  describe("detail requires an id", () => {
    test("missing id exits 1 with NO_ID", async () => {
      const result = await runCLI(["detail"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("NO_ID");
    });
  });

  describe("unknown flags are rejected, never silently dropped", () => {
    test("search with a bogus flag exits 1 with UNKNOWN_FLAG", async () => {
      const result = await runCLI(["search", "-q", "react", "--salary", "5000"]);
      expect(result.exitCode).toBe(1);
      expect(parsedStderr(result.stderr).code).toBe("UNKNOWN_FLAG");
    });

    test("detail with a search-only flag exits 1 with UNKNOWN_FLAG", async () => {
      const result = await runCLI(["detail", "A1159FCAE890A3F861373E686DCF3405", "--location", "Lima"]);
      expect(result.exitCode).toBe(1);
      expect(parsedStderr(result.stderr).code).toBe("UNKNOWN_FLAG");
    });
  });

  describe("--remote / --format validation", () => {
    test("unsupported --remote value exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-q", "react", "--remote", "anywhere"]);
      expect(result.exitCode).toBe(1);
      expect(parsedStderr(result.stderr).code).toBe("BAD_ARG");
    });

    test("unsupported --format exits 1 with BAD_ARG", async () => {
      const result = await runCLI(["search", "-q", "react", "--format", "csv"]);
      expect(result.exitCode).toBe(1);
      expect(parsedStderr(result.stderr).code).toBe("BAD_ARG");
    });
  });

  describe("unknown command", () => {
    test("exits 1 with BAD_CMD", async () => {
      const result = await runCLI(["frobnicate"]);
      expect(result.exitCode).not.toBe(0);
      const err = parsedStderr(result.stderr);
      expect(err.code).toBe("BAD_CMD");
    });
  });

  describe("existing validations (regression)", () => {
    test("all valid flags produce no BAD_ARG", async () => {
      const result = await runCLI([
        "search", "-q", "react", "-l", "Lima", "--jobage", "30", "--page", "1", "--limit", "5",
      ]);
      const err = parsedStderr(result.stderr);
      expect(err.code).not.toBe("BAD_ARG");
    });
  });
});

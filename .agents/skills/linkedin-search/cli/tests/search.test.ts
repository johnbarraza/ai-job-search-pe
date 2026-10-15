import { afterEach, describe, expect, test } from "bun:test";
import { runSearch } from "../src/commands/search";

const originalFetch = globalThis.fetch;
const originalStdoutWrite = process.stdout.write;

function searchCard(id: string, title: string): string {
  return `<li>
    <div data-entity-urn="urn:li:jobPosting:${id}">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/${id}"></a>
      <h3 class="base-search-card__title">${title}</h3>
    </div>
  </li>`;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  process.stdout.write = originalStdoutWrite;
});

describe("runSearch", () => {
  test("--limit 0 emits zero results", async () => {
    globalThis.fetch = (async () => new Response(searchCard("123456", "Engineer"))) as typeof fetch;

    let stdout = "";
    process.stdout.write = ((chunk: string | Uint8Array) => {
      stdout += chunk.toString();
      return true;
    }) as typeof process.stdout.write;

    const code = await runSearch({
      location: "Copenhagen, Denmark",
      jobage: 9999,
      page: 1,
      limit: 0,
      format: "json",
    });

    expect(code).toBe(0);
    expect(JSON.parse(stdout).results).toHaveLength(0);
  });

  test("--jobage-minutes 30 constructs f_TPR=r1800 in the request URL", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      capturedUrl = typeof input === "string" ? input : input.toString();
      return new Response("");
    }) as typeof fetch;

    const code = await runSearch({
      location: "Remote",
      jobage: 9999,
      jobageMinutes: 30,
      page: 1,
      format: "json",
    });

    expect(code).toBe(0);
    expect(capturedUrl).toContain("f_TPR=r1800");
  });
});

// Peru fork: the shared `modality` field is filled only from the work-mode filter
// the search itself applied; guest cards carry no work-mode data of their own.
describe("runSearch modality", () => {
  async function run(remote?: string) {
    globalThis.fetch = (async () => new Response(searchCard("123456", "Analista"))) as typeof fetch;
    let stdout = "";
    process.stdout.write = ((chunk: string | Uint8Array) => {
      stdout += chunk.toString();
      return true;
    }) as typeof process.stdout.write;
    await runSearch({ location: "Lima, Peru", remote, jobage: 9999, page: 1, format: "json" });
    return JSON.parse(stdout).results[0].modality;
  }

  test("set from --remote", async () => {
    expect(await run("hybrid")).toBe("híbrido");
    expect(await run("remote")).toBe("remoto");
    expect(await run("onsite")).toBe("presencial");
  });

  test("null when the search did not filter on work mode", async () => {
    expect(await run(undefined)).toBeNull();
  });
});

import { afterEach, describe, expect, test } from "bun:test";
import { apiRequest } from "../src/helpers";

// A stalled upstream connection (accepted socket, no response) would otherwise hang the
// CLI forever - fetch has no default timeout. Assert the API call carries an AbortSignal
// timeout, the honest tool-naming User-Agent, and the Peru site id.
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("apiRequest", () => {
  test("carries a timeout signal, honest UA and x-site-id BMPE; no cookie warm-up", async () => {
    const calls: Array<{ href: string; init?: RequestInit }> = [];
    globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
      const href = typeof url === "string" ? url : url instanceof URL ? url.href : url.url;
      calls.push({ href, init });
      return new Response(JSON.stringify({ total: 0, content: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;

    await apiRequest("api/avisos/searchV2?pageSize=1&page=0", {
      method: "POST",
      body: { filtros: [], query: "analista", internacional: false },
    });

    expect(calls).toHaveLength(1);
    expect(calls[0].href).toStartWith("https://www.bumeran.com.pe/api/");
    expect(calls[0].init?.signal).toBeInstanceOf(AbortSignal);
    const headers = calls[0].init?.headers as Record<string, string>;
    expect(headers["x-site-id"]).toBe("BMPE");
    expect(headers["User-Agent"]).toContain("bumeran-cli");
    expect(headers["User-Agent"]).not.toContain("Chrome");
  });
});

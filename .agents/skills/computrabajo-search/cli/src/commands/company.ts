import { fetchCompanyReviews, normalizeCompanySlug, parseCompanyReviews, writeError } from "../helpers.js"

export interface CompanyOpts {
  company: string
  area?: string
  format: "json" | "plain"
}

function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim()
}

export async function runCompany(opts: CompanyOpts): Promise<number> {
  const slug = normalizeCompanySlug(opts.company)
  if (!slug) {
    writeError(`Could not parse a company slug from "${opts.company}" (e.g. "adecco" or its pe.computrabajo.com URL)`, "BAD_ID")
    return 1
  }
  try {
    let page = await fetchCompanyReviews(slug)
    if (!page) {
      writeError("Company has no review page on Computrabajo", "NOT_FOUND")
      return 1
    }
    let reviews = parseCompanyReviews(page.html, slug, page.url)

    if (opts.area) {
      const want = fold(opts.area)
      const match = reviews.areas.find((a) => fold(a.name).includes(want) || a.path.endsWith(`-de-${want.replace(/\s+/g, "-")}`))
      if (!match) {
        const listed = reviews.areas.map((a) => `${a.name} (${a.count})`).join(", ") || "none listed"
        writeError(`No review area matches "${opts.area}". Areas: ${listed}`, "BAD_ARG")
        return 1
      }
      page = await fetchCompanyReviews(slug, match.path)
      if (!page) {
        writeError("Area review page not found", "NOT_FOUND")
        return 1
      }
      reviews = parseCompanyReviews(page.html, slug, page.url)
    }

    if (opts.format === "plain") {
      const subs = Object.entries(reviews.subratings).map(([k, v]) => `${k} ${v}`).join(" · ")
      const lines = [
        `${reviews.company ?? slug} - Computrabajo`,
        `Rating: ${reviews.rating ?? "?"} / 5 from ${reviews.reviews ?? "?"} reviews` +
          (reviews.recommendPct !== null ? ` · ${reviews.recommendPct}% recommend` : ""),
        subs ? `Subratings: ${subs}` : "",
        reviews.area
          ? `Area: ${reviews.area} · ${reviews.matching ?? "?"} reviews (the rating above is company-wide)`
          : "",
        reviews.areas.length ? `By area: ${reviews.areas.map((a) => `${a.name} ${a.count}`).join(" · ")}` : "",
        "",
        ...reviews.sample.map(
          (r) =>
            `  ${r.stars ?? "?"}★ ${r.position ?? "—"} · ${r.current === null ? "?" : r.current ? "current" : "former"} · ${r.location ?? "—"} · ${r.date ?? "—"}` +
            (r.text ? `\n     ${r.text}` : ""),
        ),
        "",
        `URL: ${reviews.url}`,
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(reviews, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "COMPANY_FAILED")
    return 1
  }
}

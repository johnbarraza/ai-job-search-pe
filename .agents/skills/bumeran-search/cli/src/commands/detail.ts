import { apiRequest, mapAvisoDetail, normalizeId, writeError, type RawAvisoDetail } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

interface RawFichaResponse {
  aviso: RawAvisoDetail
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`Could not parse a job id from "${opts.id}"`, "BAD_ID")
    return 1
  }
  try {
    const data = await apiRequest<RawFichaResponse>(`api/candidates/fichaAvisoNormalizada/${id}`, { method: "GET" })
    if (!data || !data.aviso) {
      writeError("Job not found", "NOT_FOUND")
      return 1
    }
    const job = mapAvisoDetail(data.aviso)

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}`,
        "",
        job.seniority ? `Seniority: ${job.seniority}` : "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.contractType ? `Contract: ${job.contractType}` : "",
        `Modalidad: ${job.modality}`,
        `Nivel: ${job.level}`,
        job.category ? `Category: ${job.category}` : "",
        job.date ? `Posted: ${job.date}` : "",
        job.updated ? `Updated: ${job.updated}` : "",
        job.validThrough ? `Valid through: ${job.validThrough} (portal expiry, not an employer deadline)` : "",
        job.status ? `Status: ${job.status}` : "",
        job.vacancies !== null ? `Vacancies: ${job.vacancies}` : "",
        job.address ? `Address: ${job.address}` : "",
        job.industry ? `Industry: ${job.industry}${job.companySize ? ` · ${job.companySize} employees` : ""}` : "",
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`,
        job.applyUrl ? `Apply: ${job.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED")
    return 1
  }
}

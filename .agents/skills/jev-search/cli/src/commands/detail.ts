import {
  buildDetailGoal,
  defaultRunner,
  jevArgs,
  jevCliPath,
  parseDetailAnswer,
  preflight,
  reportUnfinished,
  runJev,
  writeError,
  type Runner,
} from "../helpers.js"
import type { CommonOpts } from "./search.js"

export interface DetailOpts extends CommonOpts {
  url: string
  format: "json" | "plain"
}

export async function runDetail(opts: DetailOpts, run: Runner = defaultRunner): Promise<number> {
  const blocked = await preflight(opts.url, run)
  if (blocked !== null) return blocked
  try {
    const result = await runJev(
      jevArgs(opts.url, buildDetailGoal(), { maxSteps: opts.maxSteps, headed: opts.headed, cli: jevCliPath() }),
      opts.timeoutMs,
      run,
    )
    if (result.status !== "done" || !result.answer) return reportUnfinished(result)
    const job = parseDetailAnswer(result.answer, result.final_url ?? opts.url)
    if (opts.format === "plain") {
      const lines = [
        job.title ?? "(sin título)",
        `${job.company || "—"} · ${job.location || "—"}`,
        `Modalidad: ${job.modality}`,
        `Nivel: ${job.level}`,
        job.salary ? `Remuneración: ${job.salary}` : "",
        job.contract ? `Contrato: ${job.contract}` : "",
        job.schedule ? `Horario: ${job.schedule}` : "",
        job.deadline ? `Cierre: ${job.deadline}` : "",
        "",
        job.description ?? "(sin descripción)",
        job.requirements.length ? `\nRequisitos:\n${job.requirements.map((r) => `  - ${r}`).join("\n")}` : "",
        job.howToApply ? `\nPostulación: ${job.howToApply}` : "",
        `\nURL: ${job.url}`,
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

import { ArrowRight, CheckIcon, OptimizationIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import type { OptimizationStatus } from "@/lib/types";

export const dynamic = "force-dynamic";

const STAGES = [
  {
    step: "01",
    title: "Deterministic screening",
    detail: "Nine rules decide feasibility per pair.",
    state: "live" as const,
  },
  {
    step: "02",
    title: "Feasible opportunity set",
    detail: "Compatible and conditional links only.",
    state: "live" as const,
  },
  {
    step: "03",
    title: "CP-SAT allocation",
    detail: "Quantity, capacity, distance and timing solved together.",
    state: "planned" as const,
  },
  {
    step: "04",
    title: "Executable recovery plan",
    detail: "Per-lane allocation with binding-constraint report.",
    state: "planned" as const,
  },
];

export default async function OptimizationPage() {
  const response = await apiGet<OptimizationStatus>("/optimization");

  return (
    <>
      <PageHeader
        eyebrow="Optimization centre · allocation planning"
        title="Feasibility is solved. Allocation is next."
        description="Discovery answers “could this material work here?”. Optimization answers “how much should move, where, and in which order?” — a constraint problem the solver will own in Phase 3."
        actions={
          <span className="flex items-center gap-2 rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 font-mono text-[10px] text-ink-500">
            <OptimizationIcon className="h-3.5 w-3.5" />
            {response.ok ? response.data.engine : "OR-Tools CP-SAT"}
          </span>
        }
      />

      {!response.ok ? (
        <DataUnavailable message={response.error} title="Optimization contract unavailable" />
      ) : (
        <>
          <div className="panel mb-4 overflow-hidden">
            <div className="relative bg-forest-900 px-5 py-5 text-paper-100 sm:px-6">
              <div className="tech-grid-dark absolute inset-0 opacity-50" aria-hidden />
              <div className="relative flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-xl">
                  <div className="flex items-center gap-2">
                    <span className="flex h-2 w-2 items-center justify-center">
                      <span className="h-2 w-2 animate-pulse-soft rounded-full bg-clay-500" />
                    </span>
                    <span className="label-mono text-[9px] text-lime-400">
                      Designed · not implemented
                    </span>
                  </div>
                  <h2 className="mt-2.5 text-[19px] font-semibold tracking-[-0.01em] text-paper-50">
                    No allocation plan exists for this dataset yet.
                  </h2>
                  <p className="mt-2 text-[12px] leading-relaxed text-forest-500">
                    {response.data.status_note}
                  </p>
                </div>
                <div className="rounded-xl border border-forest-700 bg-forest-950/60 px-4 py-3">
                  <p className="label-mono text-[8.5px] text-forest-500">Engine</p>
                  <p className="mt-1 text-[13px] text-paper-100">{response.data.engine}</p>
                  <p className="mt-2 label-mono text-[8.5px] text-forest-500">Target phase</p>
                  <p className="mt-1 text-[13px] text-paper-100">{response.data.phase}</p>
                </div>
              </div>
            </div>

            <div className="grid divide-y divide-paper-200 sm:grid-cols-4 sm:divide-x sm:divide-y-0">
              {STAGES.map((stage) => (
                <div key={stage.step} className="px-4 py-3.5">
                  <div className="flex items-center justify-between">
                    <span className="figure text-[10px] text-ink-300">{stage.step}</span>
                    <Badge tone={stage.state === "live" ? "lime" : "outline"} mono>
                      {stage.state === "live" ? "live" : "planned"}
                    </Badge>
                  </div>
                  <p className="mt-2 text-[12px] font-medium text-ink-900">{stage.title}</p>
                  <p className="mt-1 text-[10.5px] leading-relaxed text-ink-400">{stage.detail}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Panel className="xl:col-span-2">
              <PanelHeader
                eyebrow="Constraint contract"
                title="What the solver must respect"
                subtitle="Hard constraints are formulated now so the Phase 3 implementation cannot loosen them."
                action={<Badge tone="warning">0 of 5 enforced</Badge>}
              />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[620px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-paper-200 bg-paper-50/60">
                      {["ID", "Constraint", "Enforced by", "Status"].map((heading) => (
                        <th
                          key={heading}
                          className="label-mono px-4 py-2.5 text-[8.5px] font-normal text-ink-400"
                        >
                          {heading}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {response.data.constraints.map((constraint) => (
                      <tr
                        key={constraint.id}
                        className="border-b border-paper-200/70 last:border-0"
                      >
                        <td className="px-4 py-3 font-mono text-[9.5px] tracking-wide text-ink-400">
                          {constraint.id}
                        </td>
                        <td className="max-w-[320px] px-4 py-3 text-[11.5px] leading-relaxed text-ink-600">
                          {constraint.description}
                        </td>
                        <td className="px-4 py-3 font-mono text-[9.5px] text-ink-400">
                          {constraint.enforced_by}
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={constraint.implemented ? "lime" : "outline"} mono>
                            {constraint.implemented ? "enforced" : "pending"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="border-t border-paper-200 px-4 py-3">
                <p className="text-[10.5px] leading-relaxed text-ink-500">
                  <span className="font-mono text-[9px] tracking-wide text-ink-400 uppercase">
                    Guardrail
                  </span>{" "}
                  — {response.data.compatibility_prerequisite}
                </p>
              </div>
            </Panel>

            <div className="space-y-4">
              <Panel>
                <PanelHeader eyebrow="Objective" title="What gets maximised" />
                <p className="px-5 py-4 text-[12px] leading-relaxed text-ink-600 sm:px-6">
                  {response.data.objective}
                </p>
              </Panel>

              <Panel>
                <PanelHeader eyebrow="Inputs" title="Solver inputs" />
                <ul className="space-y-2 px-5 py-4 sm:px-6">
                  {response.data.inputs.map((input) => (
                    <li key={input} className="flex items-start gap-2 text-[11.5px] text-ink-600">
                      <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-300" />
                      {input}
                    </li>
                  ))}
                </ul>
              </Panel>

              <Panel>
                <PanelHeader eyebrow="Outputs" title="Plan artefacts" />
                <ul className="space-y-2 px-5 py-4 sm:px-6">
                  {response.data.outputs.map((output) => (
                    <li key={output} className="flex items-start gap-2 text-[11.5px] text-ink-600">
                      <CheckIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-forest-600" />
                      {output}
                    </li>
                  ))}
                </ul>
              </Panel>
            </div>
          </div>
        </>
      )}
    </>
  );
}

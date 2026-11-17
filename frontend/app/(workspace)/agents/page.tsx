import { AgentIcon, CheckIcon, InfoIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import type { AgentRegistry } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const response = await apiGet<AgentRegistry>("/agents");

  return (
    <>
      <PageHeader
        eyebrow="Agent control centre · coordination layer"
        title="Specialists, not a chatbot."
        description="The coordination layer will use narrow, auditable agents with explicit tools and refusal boundaries. Phase 1 registers the responsibilities and guardrails; it does not run anything."
        actions={
          <span className="flex items-center gap-2 rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 font-mono text-[10px] text-ink-500">
            <span className="h-1.5 w-1.5 rounded-full bg-ink-300" />
            0 agents running
          </span>
        }
      />

      {!response.ok ? (
        <DataUnavailable message={response.error} title="Agent registry unavailable" />
      ) : (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Registered agents", value: `${response.data.agents.length}` },
              { label: "Executions enabled", value: response.data.executions_enabled ? "yes" : "no" },
              { label: "Orchestration", value: response.data.orchestration.framework },
              {
                label: "Execution records",
                value: `${response.data.executions.length}`,
              },
            ].map((item) => (
              <div key={item.label} className="panel px-4 py-3">
                <p className="label-mono text-[8.5px] text-ink-400">{item.label}</p>
                <p className="mt-1.5 text-[15px] font-medium text-ink-900">{item.value}</p>
              </div>
            ))}
          </div>

          <div className="panel mb-4 overflow-hidden">
            <div className="relative bg-forest-900 px-5 py-4 text-paper-100 sm:px-6">
              <div className="tech-grid-dark absolute inset-0 opacity-40" aria-hidden />
              <div className="relative flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-2xl">
                  <div className="flex items-center gap-2">
                    <InfoIcon className="h-4 w-4 text-lime-400" />
                    <span className="label-mono text-[9px] text-lime-400">
                      Orchestration plan · {response.data.orchestration.phase}
                    </span>
                  </div>
                  <p className="mt-2 text-[13px] leading-relaxed text-paper-200">
                    {response.data.orchestration.notes}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[9.5px] text-forest-500">
                    <span>framework · {response.data.orchestration.framework}</span>
                    <span>pattern · {response.data.orchestration.pattern}</span>
                    <span>model · {response.data.orchestration.model_provider}</span>
                    <span>state · {response.data.orchestration.persistence}</span>
                  </div>
                </div>
                <button
                  type="button"
                  disabled
                  title="Agents are not implemented in Phase 1"
                  className="cursor-not-allowed rounded-lg border border-forest-700 bg-forest-950/60 px-3 py-2 text-[11px] text-forest-500"
                >
                  Dispatch agent — {response.data.orchestration.phase}
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {response.data.agents.map((agent) => (
              <Panel key={agent.key} className="flex flex-col">
                <div className="flex items-start justify-between gap-2 border-b border-paper-200 px-4 py-3.5">
                  <div className="flex items-start gap-2.5">
                    <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg border border-forest-700/20 bg-forest-800/[0.06] text-forest-700">
                      <AgentIcon className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="text-[13px] font-semibold text-ink-900">{agent.name}</p>
                      <p className="mt-0.5 font-mono text-[8.5px] tracking-wide text-ink-400 uppercase">
                        {agent.key} · {agent.phase}
                      </p>
                    </div>
                  </div>
                  <Badge tone="outline" mono>
                    not enabled
                  </Badge>
                </div>

                <p className="px-4 py-3 text-[11.5px] leading-relaxed text-ink-600">
                  {agent.responsibility}
                </p>

                <div className="mt-auto space-y-2.5 border-t border-paper-200 px-4 py-3">
                  <div>
                    <p className="label-mono text-[8px] text-ink-400">Reads</p>
                    <p className="mt-0.5 text-[10.5px] leading-relaxed text-ink-500">
                      {agent.inputs.join(" · ")}
                    </p>
                  </div>
                  <div>
                    <p className="label-mono text-[8px] text-ink-400">Produces</p>
                    <p className="mt-0.5 text-[10.5px] leading-relaxed text-ink-500">
                      {agent.outputs.join(" · ")}
                    </p>
                  </div>
                  <div className="rounded-lg bg-paper-50 px-2.5 py-2">
                    <p className="label-mono text-[8px] text-ink-400">Guardrails</p>
                    <ul className="mt-1 space-y-1">
                      {agent.guardrails.map((guardrail) => (
                        <li
                          key={guardrail}
                          className="flex items-start gap-1.5 text-[10.5px] leading-snug text-ink-500"
                        >
                          <CheckIcon className="mt-0.5 h-3 w-3 shrink-0 text-forest-600" />
                          {guardrail}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </Panel>
            ))}
          </div>

          <Panel className="mt-4">
            <PanelHeader
              eyebrow="Execution history"
              title="Agent runs"
              subtitle="Sourced from the agent_executions table. An empty table is the honest Phase 1 state."
              action={<Badge tone="muted" mono>0 rows</Badge>}
            />
            <EmptyState
              title="No agent has ever run in this environment"
              description="Phase 1 ships the run-record schema, the registry and the guardrails. Nothing on this screen simulates agent output or AI reasoning."
            />
          </Panel>
        </>
      )}
    </>
  );
}

import { ProposalWorkspace } from "@/components/proposals/proposal-workspace";
import { DemoNotice } from "@/components/ui/demo-notice";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { ActorSwitcher } from "@/components/workflow/actor-switcher";
import { apiGet } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { loadSession } from "@/lib/session";
import type { Opportunity, Page } from "@/lib/types";
import type { ProposalSummary } from "@/lib/workflow-types";

export const dynamic = "force-dynamic";

export default async function ProposalsPage() {
  const [proposals, opportunities, session] = await Promise.all([
    apiGet<Page<ProposalSummary>>("/proposals?page_size=200"),
    apiGet<Page<Opportunity>>("/opportunities?page_size=200"),
    loadSession(),
  ]);

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Recovery proposals · approval lifecycle"
        title="From matched pair to signed decision."
        description="Every proposal moves through explicit, recorded states. Submission, review, approval, execution and verification are separate steps with separate authority — nothing is approved implicitly."
        actions={<ActorSwitcher />}
      />

      <div className="mb-4">
        <DemoNotice compact />
      </div>

      {proposals.ok ? (
        <ProposalWorkspace
          proposals={proposals.data.items}
          opportunities={opportunities.ok ? opportunities.data.items : []}
          canCreate={hasPermission(session.status === "authenticated" ? session.user : null, "proposal.create")}
        />
      ) : (
        <DataUnavailable message={proposals.error} title="Proposals unavailable" />
      )}

      <p className="mt-4 text-[10.5px] leading-relaxed text-ink-400">
        Approval requires an evidence reference and an approver who did not submit the proposal. Quantities in this workspace never count as recovered material — only verified transactions do.
      </p>
    </>
  );
}

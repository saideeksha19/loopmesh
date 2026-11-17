import type { Metadata } from "next";
import Link from "next/link";

import { ApprovalReview } from "@/components/platform/approval-review";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { formatDate, titleCase } from "@/lib/format";
import {
  PLATFORM_PERMISSION,
  approvalActionLabel,
  approvalStatusLabel,
  approvalStatusTone,
  canPlatform,
} from "@/lib/platform";
import type { PlatformApproval } from "@/lib/platform-types";
import { loadSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Approval detail",
  description: "Review a two-person platform approval request.",
  robots: { index: false, follow: false },
};

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label-mono text-[8.5px] text-ink-400">{label}</dt>
      <dd className="mt-1 text-[12px] break-words text-ink-800">{value}</dd>
    </div>
  );
}

export default async function PlatformApprovalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · approval detail"
      title="One request, one exact change."
      description="Review the recorded target, action and reason. Approval and execution are separate steps, and the API refuses any transition the current state does not allow."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.approvalsView)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="Approval detail needs platform.approvals.view"
          capability="platform.approvals.view"
          description="Your account is a platform operator without this capability, so no approval is fetched."
        />
      </>
    );
  }

  const { id } = await params;
  const response = await apiGet<PlatformApproval>(`/platform/approvals/${id}`);

  if (!response.ok) {
    return (
      <>
        {header}
        <Panel className="p-5 sm:p-6">
          <p className="label-mono text-[9px] text-ink-400">Request unavailable</p>
          <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">
            {response.status === 404
              ? "No approval request with that identifier"
              : "The approval request could not be read"}
          </h2>
          <p className="mt-1.5 max-w-xl text-[12.5px] leading-relaxed text-ink-500">
            {response.status === 404
              ? "Nothing is shown rather than a partial or invented record."
              : response.error}
          </p>
          <Link
            href="/platform/approvals"
            className="mt-4 inline-flex h-9 items-center rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100"
          >
            ← Approval queue
          </Link>
        </Panel>
      </>
    );
  }

  const approval = response.data;
  const terminal = ["executed", "rejected", "cancelled", "expired"].includes(approval.status);

  return (
    <>
      <div className="mb-4">
        <Link
          href="/platform/approvals"
          className="text-[11.5px] font-medium text-forest-700 hover:underline"
        >
          ← Approval queue
        </Link>
      </div>

      <Panel className="mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="label-mono text-[9px] text-forest-600">
              {approvalActionLabel(approval.action)} request
            </p>
            <h1 className="mt-1 truncate text-[22px] leading-tight font-semibold tracking-[-0.02em] text-ink-900">
              {approval.organization_name ?? approval.organization_id}
            </h1>
            <p className="mt-1 font-mono text-[10px] text-ink-400">{approval.id}</p>
            {approval.organization_id ? (
              <Link
                href={`/platform/organizations/${approval.organization_id}`}
                className="mt-2 inline-block text-[11.5px] text-forest-700 hover:underline"
              >
                Inspect organisation →
              </Link>
            ) : null}
          </div>
          <div className="flex flex-col items-start gap-2 sm:items-end">
            <Badge tone={approvalStatusTone(approval.status)} mono>
              {approvalStatusLabel(approval.status)}
            </Badge>
            <p className="text-[10.5px] text-ink-400">
              {approval.is_expired && approval.status === "pending"
                ? "Expired before a decision"
                : terminal
                  ? "Terminal state; no further transitions"
                  : `Expires ${formatDate(approval.expires_at)}`}
            </p>
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Panel>
          <PanelHeader
            eyebrow="Bound details"
            title="What was requested"
            subtitle="These fields are the approval's binding. A different target, action or reason cannot consume this request."
          />
          <dl className="grid gap-4 px-4 py-4 sm:grid-cols-2 sm:px-6">
            <Fact label="Target organisation" value={approval.organization_name ?? approval.organization_id} />
            <Fact label="Action" value={approvalActionLabel(approval.action)} />
            <Fact label="Requested by" value={approval.requested_by ?? approval.requested_by_user_id} />
            <Fact label="Requested at" value={formatDate(approval.created_at)} />
            <Fact label="Expires at" value={formatDate(approval.expires_at)} />
            <Fact
              label="Tenant state at execution"
              value={approval.organization_status ? titleCase(approval.organization_status) : "Unavailable"}
            />
          </dl>
          <div className="border-t border-paper-200 px-4 py-4 sm:px-6">
            <p className="label-mono text-[8.5px] text-ink-400">Reason</p>
            <p className="mt-1 text-[12px] leading-relaxed text-ink-700">
              {approval.reason ?? "No reason recorded."}
            </p>
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Review"
            title="Act on this request"
            subtitle="Approve or reject as a different operator; execute only after approval."
          />
          <div className="px-4 py-4 sm:px-6">
            <ApprovalReview approval={approval} />
          </div>
        </Panel>
      </div>

      <Panel className="mt-4">
        <PanelHeader
          eyebrow="History"
          title="Recorded transitions"
          subtitle="Every transition is appended to the audit journal. This view only reflects the current request record."
        />
        <ol className="divide-y divide-paper-200">
          <li className="px-4 py-3 sm:px-6">
            <p className="text-[11.5px] font-medium text-ink-800">Requested</p>
            <p className="mt-0.5 font-mono text-[9.5px] text-ink-400">
              {approval.requested_by ?? "—"} · {formatDate(approval.created_at)}
            </p>
          </li>
          {approval.decided_at ? (
            <li className="px-4 py-3 sm:px-6">
              <p className="text-[11.5px] font-medium text-ink-800">
                {approval.status === "rejected" ? "Rejected" : "Approved"}
              </p>
              <p className="mt-0.5 font-mono text-[9.5px] text-ink-400">
                {approval.decided_by ?? "—"} · {formatDate(approval.decided_at)}
              </p>
              {approval.decision_reason ? (
                <p className="mt-1 text-[11px] text-ink-600">{approval.decision_reason}</p>
              ) : null}
            </li>
          ) : null}
          {approval.executed_at ? (
            <li className="px-4 py-3 sm:px-6">
              <p className="text-[11.5px] font-medium text-ink-800">Executed</p>
              <p className="mt-0.5 font-mono text-[9.5px] text-ink-400">
                {approval.executed_by ?? "—"} · {formatDate(approval.executed_at)}
              </p>
            </li>
          ) : null}
          {approval.status === "cancelled" ? (
            <li className="px-4 py-3 sm:px-6">
              <p className="text-[11.5px] font-medium text-ink-800">Cancelled</p>
              <p className="mt-0.5 text-[10.5px] text-ink-400">
                The requester withdrew this request. It cannot be revived.
              </p>
            </li>
          ) : null}
          {approval.is_expired && approval.status === "pending" ? (
            <li className="px-4 py-3 sm:px-6">
              <p className="text-[11.5px] font-medium text-ink-800">Expiry reached</p>
              <p className="mt-0.5 text-[10.5px] text-ink-400">
                No decision was recorded before the expiry time. The request cannot be approved.
              </p>
            </li>
          ) : null}
        </ol>
      </Panel>
    </>
  );
}

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate, relativeTime } from "@/lib/format";
import {
  approvalActionLabel,
  approvalStatusLabel,
  approvalStatusTone,
} from "@/lib/platform";
import type { PlatformApproval } from "@/lib/platform-types";

/**
 * A request is not a change. The status badge is the only thing that says
 * whether a second operator approved it and whether it has actually run.
 */
export function ApprovalList({ items }: { items: PlatformApproval[] }) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No approval requests"
        description="Requests appear here when an operator asks for a tenant suspension or reactivation. Nothing is changed until a different operator approves it and an authorised operator executes it."
      />
    );
  }

  return (
    <ul role="list" className="divide-y divide-paper-200">
      {items.map((approval) => (
        <li key={approval.id} className="px-4 py-3.5 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={approvalStatusTone(approval.status)} mono>
              {approvalStatusLabel(approval.status)}
            </Badge>
            <Badge tone="outline" mono>
              {approvalActionLabel(approval.action)}
            </Badge>
            <Link
              href={`/platform/approvals/${approval.id}`}
              className="min-w-0 truncate text-[12px] font-medium text-ink-900 hover:underline"
            >
              {approval.organization_name ?? approval.organization_id}
            </Link>
            <span className="ml-auto font-mono text-[9.5px] whitespace-nowrap text-ink-300">
              {relativeTime(approval.created_at)}
            </span>
          </div>

          <p className="mt-1 text-[11.5px] leading-relaxed text-ink-600">
            {approval.reason ?? "No reason recorded."}
          </p>
          <p className="mt-1 font-mono text-[9px] text-ink-300">
            requested by {approval.requested_by ?? approval.requested_by_user_id.slice(0, 8)} ·{" "}
            {formatDate(approval.created_at)} · expires {formatDate(approval.expires_at)}
            {approval.decided_by ? ` · decided by ${approval.decided_by}` : ""}
            {approval.executed_at ? ` · executed ${formatDate(approval.executed_at)}` : ""}
          </p>
          {approval.is_expired && approval.status === "pending" ? (
            <p className="mt-1 text-[10.5px] text-clay-500">
              Past its expiry. It cannot be approved, rejected or executed.
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

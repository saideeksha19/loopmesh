import type { BadgeTone } from "@/components/ui/badge";
import { Badge } from "@/components/ui/badge";
import { titleCase } from "@/lib/format";

const PROPOSAL_TONES: Record<string, BadgeTone> = {
  draft: "outline",
  submitted: "neutral",
  under_review: "warning",
  approved: "forest",
  in_progress: "forest",
  completed: "lime",
  rejected: "danger",
  withdrawn: "muted",
  cancelled: "muted",
  failed: "danger",
};

const TRANSACTION_TONES: Record<string, BadgeTone> = {
  created: "outline",
  in_progress: "neutral",
  transferred: "forest",
  verified: "lime",
  rejected: "danger",
  cancelled: "muted",
  failed: "danger",
};

export function ProposalStatusBadge({ status }: { status: string }) {
  return <Badge tone={PROPOSAL_TONES[status] ?? "neutral"}>{titleCase(status)}</Badge>;
}

export function TransactionStatusBadge({ status }: { status: string }) {
  return <Badge tone={TRANSACTION_TONES[status] ?? "neutral"}>{titleCase(status)}</Badge>;
}

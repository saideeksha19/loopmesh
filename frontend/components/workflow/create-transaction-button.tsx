"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { postJson } from "@/lib/client-api";
import type { TransactionDetail } from "@/lib/workflow-types";

export function CreateTransactionButton({
  proposalId,
  canCreate,
}: {
  proposalId: string;
  canCreate: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setPending(true);
    setError(null);
    const result = await postJson<TransactionDetail>("/transactions", {
      proposal_id: proposalId,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    router.push(`/transactions/${result.data.id}`);
    router.refresh();
  }

  if (!canCreate) return null;

  return (
    <div>
      <button
        type="button"
        onClick={create}
        disabled={pending}
        className="rounded-lg bg-forest-800 px-3 py-1.5 text-[11.5px] font-medium text-paper-50 disabled:opacity-60"
      >
        {pending ? "Creating…" : "Create transaction"}
      </button>
      <p className="mt-2 text-[10px] leading-relaxed text-ink-300">
        Requires coordinator or approver authority and an approved proposal. Creating it moves the
        proposal into execution.
      </p>
      {error ? (
        <p className="mt-2 rounded-lg border border-rust-500/30 bg-rust-500/10 px-3 py-2 text-[11px] text-rust-500">
          {error}
        </p>
      ) : null}
    </div>
  );
}

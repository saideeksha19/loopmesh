import { TransactionWorkspace } from "@/components/transactions/transaction-workspace";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { DemoNotice } from "@/components/ui/demo-notice";
import { PageHeader } from "@/components/ui/page-header";
import { ActorSwitcher } from "@/components/workflow/actor-switcher";
import { apiGet } from "@/lib/api";
import type { Page } from "@/lib/types";
import type { TransactionSummary } from "@/lib/workflow-types";

export const dynamic = "force-dynamic";

export default async function TransactionsPage() {
  const response = await apiGet<Page<TransactionSummary>>("/transactions?page_size=200");

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Recovery transactions · execution and verification"
        title="Evidence decides what counts."
        description="A recorded transfer is not recovered material. Only a verified transaction with a weighbridge ticket or equivalent evidence contributes to the impact ledger, and the verifier must not be the person who recorded the transfer."
        actions={<ActorSwitcher />}
      />

      <div className="mb-4">
        <DemoNotice compact />
      </div>

      {response.ok ? (
        <TransactionWorkspace transactions={response.data.items} />
      ) : (
        <DataUnavailable message={response.error} title="Transactions unavailable" />
      )}
    </>
  );
}

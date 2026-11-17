import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

import { MaterialsWorkspace } from "@/components/materials/materials-workspace";
import { ProposalWorkspace } from "@/components/proposals/proposal-workspace";
import { CreateTransactionButton } from "@/components/workflow/create-transaction-button";

function materialWorkspace(canCreate: boolean, canImport: boolean) {
  return render(
    <MaterialsWorkspace
      initialMaterials={[]}
      organizations={[]}
      canCreate={canCreate}
      canImport={canImport}
    />,
  );
}

function proposalWorkspace(canCreate: boolean) {
  return render(
    <ProposalWorkspace proposals={[]} opportunities={[]} canCreate={canCreate} />,
  );
}

describe("read-only role affordances", () => {
  it("hides material creation and import controls when the role lacks both permissions", () => {
    materialWorkspace(false, false);

    expect(screen.queryByRole("button", { name: /add material/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /import csv/i })).toBeNull();
    // Read-only users keep the read affordances they are entitled to.
    expect(
      screen.getByRole("textbox", { name: /search material streams/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by status/i)).toBeInTheDocument();
  });

  it("hides only the import control when the role can create but not import", () => {
    materialWorkspace(true, false);

    expect(screen.getByRole("button", { name: /add material/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /import csv/i })).toBeNull();
  });

  it("hides only the create control when the role can import but not create", () => {
    materialWorkspace(false, true);

    expect(screen.queryByRole("button", { name: /add material/i })).toBeNull();
    expect(screen.getByRole("button", { name: /import csv/i })).toBeInTheDocument();
  });

  it("keeps both material actions for an operator holding material.create and material.import", () => {
    materialWorkspace(true, true);

    expect(screen.getByRole("button", { name: /add material/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import csv/i })).toBeInTheDocument();
  });

  it("hides New draft proposal when the role lacks proposal.create", () => {
    proposalWorkspace(false);

    expect(screen.queryByRole("button", { name: /new draft proposal/i })).toBeNull();
    // The proposal register itself stays readable.
    expect(screen.getByRole("textbox", { name: /search proposals/i })).toBeInTheDocument();
  });

  it("keeps New draft proposal for a role holding proposal.create", () => {
    proposalWorkspace(true);

    expect(screen.getByRole("button", { name: /new draft proposal/i })).toBeInTheDocument();
  });

  it("hides Create transaction when the role lacks transaction.create", () => {
    render(<CreateTransactionButton proposalId="p-1" canCreate={false} />);

    expect(screen.queryByRole("button", { name: /create transaction/i })).toBeNull();
  });

  it("keeps Create transaction for coordinator/approver authority", () => {
    render(<CreateTransactionButton proposalId="p-1" canCreate />);

    expect(screen.getByRole("button", { name: /create transaction/i })).toBeInTheDocument();
  });
});

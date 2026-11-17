import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getJson } = vi.hoisted(() => ({ getJson: vi.fn() }));

vi.mock("@/lib/client-api", () => ({ getJson }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

import { MaterialsWorkspace } from "@/components/materials/materials-workspace";
import type { MaterialDetail, MaterialSummary } from "@/lib/types";

const organization = {
  id: "org-1",
  name: "E2E Tenant Org",
  slug: "e2e-tenant-org",
  sector: "manufacturing",
  city: "Rotterdam",
  country: "NL",
  is_demo: false,
};

const summary: MaterialSummary = {
  id: "mat-1",
  reference_code: "MF-0001",
  name: "Slag fines",
  category: "slag",
  quantity_available: 120,
  unit: "t",
  condition: "dry",
  status: "available",
  hazard_class: null,
  organization,
  availability_start: null,
  availability_end: null,
  data_source: "demo",
  is_demo: true,
  created_at: "2026-01-01T00:00:00Z",
};

const detail: MaterialDetail = {
  ...summary,
  description: null,
  handling_requirements: null,
  origin_process: null,
  specification: null,
  opportunity_count: 0,
};

function renderWorkspace() {
  return render(
    <MaterialsWorkspace
      initialMaterials={[summary]}
      organizations={[]}
      canCreate={false}
      canImport={false}
    />,
  );
}

function rowButton() {
  return screen.getByRole("button", {
    name: "Open material detail: Slag fines (MF-0001)",
  });
}

async function openDrawer(keys: string) {
  renderWorkspace();
  const trigger = rowButton();
  trigger.focus();
  await userEvent.keyboard(keys);
  await waitFor(() => expect(getJson).toHaveBeenCalledWith("/materials/mat-1"));
  return { trigger, dialog: await screen.findByRole("dialog", { name: /material detail/i }) };
}

beforeEach(() => {
  getJson.mockReset();
  getJson.mockResolvedValue({ ok: true, data: detail });
});

describe("material register keyboard operability", () => {
  it("exposes each interactive row as a named button that announces a dialog", () => {
    renderWorkspace();

    const trigger = rowButton();
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(trigger.tagName).toBe("BUTTON");
  });

  it("opens the material detail drawer with Enter", async () => {
    const { dialog } = await openDrawer("{Enter}");

    expect(dialog).toHaveAttribute("aria-modal", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Slag fines" })).toBeVisible());
  });

  it("opens the material detail drawer with Space", async () => {
    await openDrawer(" ");

    expect(getJson).toHaveBeenCalledTimes(1);
  });

  it("moves focus into the drawer when it opens", async () => {
    await openDrawer("{Enter}");

    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("closes on Escape and returns focus to the originating row", async () => {
    const { trigger, dialog } = await openDrawer("{Enter}");

    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("keeps pointer activation on the row itself", async () => {
    renderWorkspace();

    await userEvent.click(screen.getByText("E2E Tenant Org"));

    await waitFor(() => expect(getJson).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("dialog", { name: /material detail/i })).toBeInTheDocument();
  });
});

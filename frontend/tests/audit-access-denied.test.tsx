import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock("@/lib/api", () => ({ apiGet: api.apiGet }));

import AuditPage from "@/app/(workspace)/audit/page";

async function renderAudit() {
  const page = await AuditPage({ searchParams: Promise.resolve({}) });
  return render(page);
}

describe("audit journal error states", () => {
  beforeEach(() => {
    api.apiGet.mockReset();
  });

  it("renders access-denied messaging without developer instructions on 403", async () => {
    api.apiGet.mockResolvedValue({
      ok: false,
      error: "You do not have permission to perform this action.",
      status: 403,
      code: "forbidden",
      reason: "insufficient_permission",
    });

    await renderAudit();

    expect(screen.getByRole("heading", { name: /access denied/i })).toBeInTheDocument();
    expect(screen.getByText(/does not include audit-journal visibility/i)).toBeInTheDocument();
    expect(screen.getByText(/ask an organisation administrator/i)).toBeInTheDocument();

    // Developer setup guidance must not appear for an authorization outcome.
    expect(screen.queryByText(/uvicorn/i)).toBeNull();
    expect(screen.queryByText(/seed_demo/i)).toBeNull();
    expect(screen.queryByText(/start the api/i)).toBeNull();
    // Filters would only repeat the same 403.
    expect(screen.queryByRole("link", { name: /^all entities$/i })).toBeNull();
  });

  it("keeps troubleshooting guidance when the API is genuinely unreachable", async () => {
    api.apiGet.mockResolvedValue({
      ok: false,
      error: "The LOOPMESH API is not reachable.",
    });

    await renderAudit();

    expect(screen.getByRole("heading", { name: /audit journal unavailable/i })).toBeInTheDocument();
    expect(screen.getByText(/start the api/i)).toBeInTheDocument();
    expect(screen.getByText(/seed_demo/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /access denied/i })).toBeNull();
  });

  it("keeps troubleshooting guidance for a server-side failure", async () => {
    api.apiGet.mockResolvedValue({
      ok: false,
      error: "API responded with 500",
      status: 500,
    });

    await renderAudit();

    expect(screen.getByRole("heading", { name: /audit journal unavailable/i })).toBeInTheDocument();
    expect(screen.getByText(/uvicorn/i)).toBeInTheDocument();
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { NetworkCanvas } from "@/components/network/network-canvas";
import type { NetworkGraph } from "@/lib/types";

const graph: NetworkGraph = {
  nodes: [
    {
      id: "org-a",
      name: "Northfield Steel",
      slug: "northfield-steel",
      sector: "manufacturing",
      city: "Rotterdam",
      country: "NL",
      is_demo: true,
      material_streams: 3,
      open_demands: 1,
      outbound_links: 1,
      inbound_links: 0,
    },
    {
      id: "org-b",
      name: "Delta Aggregates",
      slug: "delta-aggregates",
      sector: "mining",
      city: null,
      country: "BE",
      is_demo: true,
      material_streams: 0,
      open_demands: 2,
      outbound_links: 0,
      inbound_links: 1,
    },
  ],
  edges: [
    {
      id: "edge-1",
      source: "org-a",
      target: "org-b",
      category: "slag",
      status: "confirmed",
      opportunity_count: 1,
      confirmed_transactions: 1,
      quantity_by_unit: [{ unit: "t", quantity: 120 }],
    },
  ],
  summary: {
    organizations: 2,
    potential_links: 0,
    confirmed_links: 1,
    total_material_streams: 3,
    unlinked_organizations: 0,
  },
  legend: {},
};

function node(name: string) {
  return screen.getByRole("button", { name: new RegExp(`^${name},`) });
}

function focusRing(name: string) {
  return node(name).querySelector(".net-node-focus-ring");
}

function renderCanvas() {
  return render(<NetworkCanvas graph={graph} />);
}

/** jsdom cannot focus an SVG <g>, so drive the component's focus source directly. */
function setActiveElement(element: Element | null) {
  Object.defineProperty(document, "activeElement", {
    configurable: true,
    get: () => element,
  });
}

function keyboardFocusOn(element: Element) {
  setActiveElement(element);
  fireEvent.keyDown(document, { key: "Tab" });
}

afterEach(() => {
  Reflect.deleteProperty(document, "activeElement");
});

describe("network canvas node keyboard focus", () => {
  it("keeps every node keyboard reachable and named", () => {
    renderCanvas();

    expect(node("Northfield Steel")).toHaveAttribute("tabindex", "0");
    expect(node("Delta Aggregates")).toHaveAttribute("tabindex", "0");
    expect(node("Northfield Steel")).toHaveAttribute(
      "aria-label",
      "Northfield Steel, 3 streams, 1 outbound lanes",
    );
  });

  it("still activates a node with Enter", () => {
    renderCanvas();
    const target = node("Northfield Steel");

    fireEvent.keyDown(target, { key: "Enter" });

    expect(target).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Selected organisation")).toBeInTheDocument();
  });

  it("still activates a node with Space", () => {
    renderCanvas();
    const target = node("Delta Aggregates");

    fireEvent.keyDown(target, { key: " " });

    expect(target).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Selected organisation")).toBeInTheDocument();
  });

  it("gives each node a dedicated lime ring shape, hidden by default", () => {
    renderCanvas();

    const ring = focusRing("Northfield Steel");
    expect(ring).not.toBeNull();
    expect(ring).toHaveAttribute("fill", "none");
    expect(ring).toHaveAttribute("stroke", "var(--color-lime-400)");
    expect(ring).toHaveAttribute("stroke-width", "2");
    expect(ring).toHaveAttribute("opacity", "0");
    expect(ring).toHaveClass("pointer-events-none");
  });

  it("raises the ring for keyboard focus and clears it when focus leaves", async () => {
    renderCanvas();

    keyboardFocusOn(node("Northfield Steel"));

    await waitFor(() => expect(focusRing("Northfield Steel")).toHaveAttribute("opacity", "1"));
    expect(focusRing("Delta Aggregates")).toHaveAttribute("opacity", "0");

    setActiveElement(null);
    fireEvent.keyDown(document, { key: "Tab" });

    await waitFor(() => expect(focusRing("Northfield Steel")).toHaveAttribute("opacity", "0"));
  });

  it("does not raise the ring from pointer interaction", async () => {
    renderCanvas();
    const target = node("Northfield Steel");

    keyboardFocusOn(target);
    await waitFor(() => expect(focusRing("Northfield Steel")).toHaveAttribute("opacity", "1"));

    fireEvent.pointerDown(target);
    fireEvent.click(target);

    await waitFor(() => expect(focusRing("Northfield Steel")).toHaveAttribute("opacity", "0"));
    expect(target).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps selected and focused states structurally distinct", async () => {
    renderCanvas();
    const target = node("Northfield Steel");

    fireEvent.keyDown(target, { key: "Enter" });

    // Selection is drawn by the node's own stroke and lime halo, not by the focus ring.
    const halo = target.querySelector("circle");
    expect(halo).toHaveAttribute("fill", "var(--color-lime-400)");
    expect(halo).toHaveAttribute("opacity", "0.12");
    expect(focusRing("Northfield Steel")).toHaveAttribute("opacity", "0");
    expect(node("Delta Aggregates")).toHaveAttribute("aria-pressed", "false");

    // Focusing the selected node adds the ring without replacing the selection halo.
    keyboardFocusOn(target);

    await waitFor(() => expect(focusRing("Northfield Steel")).toHaveAttribute("opacity", "1"));
    expect(halo).toHaveAttribute("opacity", "0.12");
  });
});

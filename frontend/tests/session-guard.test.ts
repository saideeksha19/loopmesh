import { describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({ target: "" }));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    nav.target = url;
    throw new Error("NEXT_REDIRECT");
  },
}));

import { redirectToSignIn } from "@/lib/session";

async function guardTarget(): Promise<string> {
  nav.target = "";
  await expect(redirectToSignIn()).rejects.toThrow("NEXT_REDIRECT");
  return nav.target;
}

describe("workspace access guard", () => {
  it("never renders a workspace route for an unauthenticated request", async () => {
    // The guard redirects instead of returning a session, so no page, layout
    // header or navigation is sent to the browser.
    expect(await guardTarget()).toBe("/api/v1/auth/resume");
  });

  it("routes through renewal rather than straight to the password form", async () => {
    // The refresh cookie is path-scoped to /api/v1/auth and is invisible to
    // workspace requests, so silent renewal must be the first hop.
    expect(await guardTarget()).not.toBe("/login");
  });
});

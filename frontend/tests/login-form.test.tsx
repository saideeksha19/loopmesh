import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";

const router = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

type Call = { url: string; init: RequestInit };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const SIGNED_IN = {
  message: "Signed in.",
  authenticated: true,
  user: { id: "u1", email: "ada@aurelia.example", full_name: "Ada Ortega" },
};

function mockFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      calls.push({ url, init });
      return handler(url, init);
    }),
  );
  return calls;
}

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  if (email) await user.type(screen.getByLabelText("Work email"), email);
  if (password) await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("sign-in form", () => {
  beforeEach(() => {
    router.replace.mockReset();
    router.refresh.mockReset();
  });

  it("signs in with valid credentials and continues to the requested page", async () => {
    const calls = mockFetch(() => jsonResponse(200, SIGNED_IN));

    render(<LoginForm next="/proposals" />);
    await fillAndSubmit("ada@aurelia.example", "correct horse battery");

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/proposals"));
    expect(router.refresh).toHaveBeenCalled();

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/auth/login");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      email: "ada@aurelia.example",
      password: "correct horse battery",
    });
  });

  it("shows a generic error for invalid credentials and clears the password", async () => {
    mockFetch(() =>
      jsonResponse(401, {
        error: {
          code: "authentication_error",
          message: "Invalid email or password.",
          details: { reason: "invalid_credentials" },
        },
      }),
    );

    render(<LoginForm next="/overview" />);
    await fillAndSubmit("ada@aurelia.example", "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("blocks submission and focuses the first invalid field", async () => {
    const calls = mockFetch(() => jsonResponse(200, SIGNED_IN));

    render(<LoginForm next="/overview" />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByText("Enter the email address on your account.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toHaveFocus();
    expect(calls).toHaveLength(0);
  });

  it("rejects a malformed email before calling the API", async () => {
    const calls = mockFetch(() => jsonResponse(200, SIGNED_IN));

    render(<LoginForm next="/overview" />);
    await fillAndSubmit("not-an-email", "some-password");

    expect(
      screen.getByText("Enter a valid email address, for example name@company.com."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toHaveAttribute("aria-invalid", "true");
    expect(calls).toHaveLength(0);
  });

  it("surfaces a network interruption without navigating", async () => {
    mockFetch(() => {
      throw new TypeError("Failed to fetch");
    });

    render(<LoginForm next="/overview" />);
    await fillAndSubmit("ada@aurelia.example", "correct horse battery");

    expect(await screen.findByRole("alert")).toHaveTextContent("not reachable");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("surfaces a CSRF rejection from the API", async () => {
    mockFetch(() =>
      jsonResponse(403, {
        error: { code: "csrf_failed", message: "CSRF validation failed." },
      }),
    );

    render(<LoginForm next="/overview" />);
    await fillAndSubmit("ada@aurelia.example", "correct horse battery");

    expect(await screen.findByRole("alert")).toHaveTextContent("CSRF validation failed.");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("ignores an off-site redirect target", async () => {
    mockFetch(() => jsonResponse(200, SIGNED_IN));

    render(<LoginForm next="//attacker.example/steal" />);
    await fillAndSubmit("ada@aurelia.example", "correct horse battery");

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/overview"));
  });
});

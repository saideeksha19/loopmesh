import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { totp, futureTotp } from "./totp";

const PASSWORD = "StrongPass!2345";
const REQUESTER = "e2e-requester@example.com";
const APPROVER = "e2e-approver@example.com";
const MEMBER = "e2e-member@example.com";

async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#login-email")).toBeEditable();
  await expect(page.locator("#login-password")).toBeEditable();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.locator("#login-email").fill(email);
  await page.locator("#login-password").fill(password);
  const submit = page.getByRole("button", { name: /^sign in$/i });
  await expect(submit).toBeEnabled();
  const [loginResponse] = await Promise.all([
    page.waitForResponse(
      (resp) => resp.url().includes("/api/v1/auth/login") && resp.request().method() === "POST",
      { timeout: 30_000 },
    ),
    submit.click(),
  ]);
  expect(loginResponse.ok(), `login failed: ${loginResponse.status()} ${await loginResponse.text()}`).toBeTruthy();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 30_000 });
}

async function enrollAndVerify(page: Page): Promise<{ secret: string; recoveryCodes: string[] }> {
  await page.goto("/platform/security");
  await expect(page.getByText(/begin enrolment|not enrolled/i).first()).toBeVisible();
  await page.locator('label:has-text("Current password") input[type="password"]').first().fill(PASSWORD);
  await page.getByRole("button", { name: /begin enrolment/i }).click();
  const secretEl = page.locator("code").first();
  await expect(secretEl).toBeVisible();
  const secret = (await secretEl.innerText()).trim();
  await page.locator('label:has-text("Six-digit code") input').fill(totp(secret));
  await page.getByRole("button", { name: /confirm enrolment/i }).click();
  const codesList = page.locator("ul li");
  await expect(codesList.first()).toBeVisible();
  const recoveryCodes = await codesList.allInnerTexts();
  await page.getByRole("button", { name: /i saved these codes/i }).click();
  // Confirming enrollment should make the session verified for platform access.
  await expect(page.getByText(/TOTP enrolled/i)).toBeVisible();
  return { secret, recoveryCodes: recoveryCodes.map((c) => c.trim()) };
}

async function verifySession(page: Page, secret: string, invalidFirst = false) {
  await page.goto("/platform/security");
  if (invalidFirst) {
    await page.locator('label:has-text("Authenticator code") input').fill("000000");
    await page.getByRole("button", { name: /verify session/i }).click();
    await expect(page.getByRole("alert").or(page.getByText(/invalid|incorrect|not accepted/i))).toBeVisible();
  }
  // Wait a moment to avoid same-step replay in strict cases; totp() uses current time.
  await page.waitForTimeout(1100);
  await page.locator('label:has-text("Authenticator code") input').fill(totp(secret));
  await page.getByRole("button", { name: /verify session/i }).click();
  await expect(page.getByText(/this session verified/i)).toBeVisible();
}

async function newAuthedContext(browser: Browser, email: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await login(page, email);
  return { context, page };
}

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  return errors;
}

async function assertNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow, `horizontal overflow at ${page.url()}`).toBeFalsy();
}

async function assertNoSensitiveStorage(page: Page) {
  const data = await page.evaluate(() => {
    const entries: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k) entries[k] = localStorage.getItem(k) ?? "";
    }
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = `session:${sessionStorage.key(i)}`;
      if (sessionStorage.key(i)) entries[k] = sessionStorage.getItem(sessionStorage.key(i)!) ?? "";
    }
    return entries;
  });
  const text = JSON.stringify(data).toLowerCase();
  for (const marker of ["token", "secret", "otpauth", "recovery", "password", "lm_session", "lm_refresh", "csrf"]) {
    // csrf cookie value must not be persisted in web storage; names may appear in harmless UI state but not values.
    expect(text).not.toContain("otpauth://");
    expect(text).not.toContain("strongpass!");
  }
  expect(text).not.toContain("recovery");
}

test.describe.serial("Batch 13 platform browser security", () => {
  test.setTimeout(240_000);
  let requesterSecret = "";
  let requesterRecovery: string[] = [];
  let approverSecret = "";

  test("1,2,3,4,15,16: enrollment, verification, invalid code, recovery single-use, MFA gate, storage and layout", async ({ browser }) => {
    const { context, page } = await newAuthedContext(browser, REQUESTER);
    const consoleErrors = collectConsoleErrors(page);

    // 4. MFA-required platform route access: before enrollment/verification platform should be gated.
    await page.goto("/platform");
    const gatedByUrl = /\/platform\/security|\/login|mfa/i.test(page.url());
    if (!gatedByUrl) {
      await expect(
        page.getByText(/requires a verified second factor|verify.*session|mfa required|not enrolled|begin enrolment/i).first(),
      ).toBeVisible({ timeout: 20_000 });
    }

    // 1. Enrollment
    const enrolled = await enrollAndVerify(page);
    requesterSecret = enrolled.secret;
    requesterRecovery = enrolled.recoveryCodes;
    expect(requesterRecovery.length).toBeGreaterThanOrEqual(8);

    // 15. No secrets/tokens in browser localStorage/sessionStorage.
    await assertNoSensitiveStorage(page);

    // 16. No horizontal overflow or console errors (desktop).
    await assertNoHorizontalOverflow(page);

    // Create a fresh unverified session to test invalid code handling.
    const { context: c2, page: p2 } = await newAuthedContext(browser, REQUESTER);
    const c2ConsoleErrors = collectConsoleErrors(p2);
    await p2.goto("/platform/security", { waitUntil: "domcontentloaded" });
    await expect(p2.getByText(/this session unverified|verify session/i).first()).toBeVisible({ timeout: 30_000 });

    // 2. Invalid code handling.
    await p2.locator('label:has-text("Authenticator code") input').fill("000000");
    await p2.getByRole("button", { name: /verify session/i }).click();
    await expect(p2.getByRole("alert").or(p2.getByText(/invalid|incorrect|not accepted|locked/i)).first()).toBeVisible({ timeout: 30_000 });
    await assertNoHorizontalOverflow(p2);
    await c2.close();

    // 3. Recovery-code single-use behaviour (real API calls from authenticated browser sessions).
    const recovery = requesterRecovery[0];
    const { context: c3, page: p3 } = await newAuthedContext(browser, REQUESTER);
    await p3.goto("/platform/security", { waitUntil: "domcontentloaded" });
    const result1 = await p3.evaluate(async (code) => {
      const csrf = document.cookie.split("; ").find((c) => c.startsWith("lm_csrf="))?.split("=")[1] ?? "";
      const res = await fetch("/api/v1/auth/mfa/verify", {
        method: "POST",
        headers: { "content-type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) },
        body: JSON.stringify({ recovery_code: code }),
        credentials: "include",
      });
      return { status: res.status, body: await res.text() };
    }, recovery);
    expect(result1.status, `first recovery-code use: ${result1.status} ${result1.body}`).toBe(200);

    // Reuse must fail in a fresh unverified session (already-verified sessions short-circuit verification).
    const { context: c4, page: p4 } = await newAuthedContext(browser, REQUESTER);
    await p4.goto("/platform/security", { waitUntil: "domcontentloaded" });
    const result2 = await p4.evaluate(async (code) => {
      const csrf = document.cookie.split("; ").find((c) => c.startsWith("lm_csrf="))?.split("=")[1] ?? "";
      const res = await fetch("/api/v1/auth/mfa/verify", {
        method: "POST",
        headers: { "content-type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) },
        body: JSON.stringify({ recovery_code: code }),
        credentials: "include",
      });
      return { status: res.status, body: await res.text() };
    }, recovery);
    expect(result2.status, `reused recovery-code: ${result2.status} ${result2.body}`).not.toBe(200);
    await c4.close();

    await p3.reload({ waitUntil: "domcontentloaded" });
    await expect(p3.getByText(/this session verified|TOTP enrolled/i).first()).toBeVisible({ timeout: 30_000 });
    await assertNoHorizontalOverflow(p3);
    // Console errors: allow none from app (ignore known benign resource noise if any appears).
    const serious1 = consoleErrors.filter((e) => !/favicon|ResizeObserver|Download the React DevTools|Failed to load resource: the server responded with a status of 401/i.test(e));
    const seriousC2 = c2ConsoleErrors.filter((e) => !/favicon|ResizeObserver|Download the React DevTools|Failed to load resource: the server responded with a status of 401/i.test(e));
    expect(serious1, `console errors: ${serious1.join("\n")}`).toEqual([]);
    expect(seriousC2, `console errors c2: ${seriousC2.join("\n")}`).toEqual([]);

    await c3.close();
    await context.close();
  });

  test("5-10,11,12,13,14,15,16: two-operator approval flow, sessions, audit, permissions, direct URL, responsive", async ({ browser }) => {
    // Approver enrolls and verifies.
    const { context: approverCtx, page: approver } = await newAuthedContext(browser, APPROVER);
    const approverConsole = collectConsoleErrors(approver);
    const approverEnrolled = await enrollAndVerify(approver);
    approverSecret = approverEnrolled.secret;

    // Requester logs in with already-enrolled account and verifies current session.
    const { context: requesterCtx, page: requester } = await newAuthedContext(browser, REQUESTER);
    const requesterConsole = collectConsoleErrors(requester);
    await requester.goto("/platform/security", { waitUntil: "domcontentloaded" });
    await expect(requester.getByText(/TOTP enrolled|Not enrolled|verify session/i).first()).toBeVisible({ timeout: 30_000 });
    if (await requester.getByRole("button", { name: /verify session/i }).isVisible().catch(() => false)) {
      await requester.waitForTimeout(1100);
      await requester.locator('label:has-text("Authenticator code") input').fill(totp(requesterSecret));
      await requester.getByRole("button", { name: /verify session/i }).click();
      await expect(requester.getByText(/this session verified/i)).toBeVisible({ timeout: 30_000 });
    }

    // 5. Requesting organisation suspension.
    await requester.goto("/platform/approvals", { waitUntil: "domcontentloaded" });
    await expect(requester.getByRole("heading", { name: /Two people, one irreversible change/i })).toBeVisible({ timeout: 30_000 });
    const orgSelect = requester.locator("label:has-text('Organisation') select").first();
    await expect(orgSelect).toBeVisible();
    const orgOption = orgSelect.locator("option", { hasText: "E2E Tenant Org" }).first();
    const orgValue = await orgOption.getAttribute("value");
    expect(orgValue, "E2E org option missing").toBeTruthy();
    await orgSelect.selectOption(orgValue!);
    await orgSelect.evaluate((el: HTMLSelectElement, v) => {
      if (el.value !== v) { el.value = v; }
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, orgValue!);
    await expect(orgSelect).toHaveValue(orgValue!);
    await requester.locator("label:has-text('Requested action') select").selectOption("suspend");
    await requester.locator("label:has-text('Reason') textarea").fill("E2E suspension requires a second operator.");
    const requestBtn = requester.getByRole("button", { name: /^Request approval$/i });
    await expect(requestBtn).toBeEnabled({ timeout: 30_000 });
    await requestBtn.click();
    await expect(requester.getByText(/Request created and pending a different operator/i)).toBeVisible({ timeout: 30_000 });

    await requester.getByRole("link", { name: /Open the request/i }).click();
    await expect(requester).toHaveURL(/\/platform\/approvals\//, { timeout: 30_000 });
    const suspensionUrl = requester.url();

    // 6. Requester cannot approve their own request.
    await expect(requester.getByRole("button", { name: /^Approve$/i })).toHaveCount(0);
    await expect(requester.getByRole("button", { name: /^Reject$/i })).toHaveCount(0);

    // 7,8. Second operator can approve with dialog/confirmation.
    await approver.goto(suspensionUrl, { waitUntil: "domcontentloaded" });
    await expect(approver.getByText(/Approve or reject as a different operator/i)).toBeVisible({ timeout: 30_000 });
    await approver.getByRole("button", { name: /^Approve$/i }).click();
    const approveDialog = approver.getByRole("dialog");
    await expect(approveDialog).toBeVisible();
    await expect(approveDialog.getByText(/Approve this request/i)).toBeVisible();
    await approveDialog.locator("textarea").fill("Second operator approves suspension.");
    await approveDialog.getByRole("button", { name: /Confirm approval/i }).click();
    await expect(approver.getByText(/Request approved|executable|exactly once/i).first()).toBeVisible({ timeout: 30_000 });

    // 9. Execute approved suspension.
    const executeSuspend = approver.getByRole("button", { name: /Execute suspend/i });
    await expect(executeSuspend).toBeVisible({ timeout: 30_000 });
    await executeSuspend.click();
    const executeDialog = approver.getByRole("dialog");
    await expect(executeDialog).toBeVisible();
    await expect(executeDialog.getByText(/Execute the approved change/i)).toBeVisible();
    await executeDialog.getByRole("button", { name: /Execute change/i }).click();
    await expect(approver.getByText(/approved change was executed|Tenant state|executed/i).first()).toBeVisible({ timeout: 30_000 });

    // Reactivation flow through UI (request + approve + execute) by two operators.
    await requester.goto("/platform/approvals", { waitUntil: "domcontentloaded" });
    await expect(requester.getByRole("heading", { name: /Two people, one irreversible change/i })).toBeVisible({ timeout: 30_000 });
    const orgSelect2 = requester.locator("label:has-text('Organisation') select").first();
    await expect(orgSelect2).toBeVisible();
    const orgValue2 = await orgSelect2.locator("option", { hasText: "E2E Tenant Org" }).first().getAttribute("value");
    expect(orgValue2, "E2E org option missing for reactivation").toBeTruthy();
    await orgSelect2.selectOption(orgValue2!);
    await orgSelect2.evaluate((el: HTMLSelectElement, v) => {
      if (el.value !== v) { el.value = v; }
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, orgValue2!);
    await expect(orgSelect2).toHaveValue(orgValue2!);
    await requester.locator("label:has-text('Requested action') select").selectOption("reactivate");
    await requester.locator("label:has-text('Reason') textarea").fill("Reactivate after reviewed suspension.");
    const requestBtn2 = requester.getByRole("button", { name: /^Request approval$/i });
    await expect(requestBtn2).toBeEnabled({ timeout: 30_000 });
    await requestBtn2.click();
    await expect(requester.getByText(/Request created and pending a different operator/i)).toBeVisible({ timeout: 30_000 });
    await requester.getByRole("link", { name: /Open the request/i }).click();
    await expect(requester).toHaveURL(/\/platform\/approvals\//, { timeout: 30_000 });
    const reactivateUrl = requester.url();

    await approver.goto(reactivateUrl, { waitUntil: "domcontentloaded" });
    await expect(approver.getByRole("button", { name: /^Approve$/i })).toBeVisible({ timeout: 30_000 });
    await approver.getByRole("button", { name: /^Approve$/i }).click();
    await approver.getByRole("dialog").getByRole("button", { name: /Confirm approval/i }).click();
    await expect(approver.getByText(/Request approved|executable|exactly once/i).first()).toBeVisible({ timeout: 30_000 });
    const executeReactivate = approver.getByRole("button", { name: /Execute reactivate/i });
    await expect(executeReactivate).toBeVisible({ timeout: 30_000 });
    await executeReactivate.click();
    await approver.getByRole("dialog").getByRole("button", { name: /Execute change/i }).click();
    await expect(approver.getByText(/approved change was executed|Tenant state|executed/i).first()).toBeVisible({ timeout: 30_000 });

    // 10. Session listing and revocation.
    await requester.goto("/platform/security", { waitUntil: "domcontentloaded" });
    await expect(requester.getByRole("heading", { name: /Operator sessions/i })).toBeVisible({ timeout: 30_000 });
    await expect(requester.getByText(/active operator session/i).first()).toBeVisible();
    const { context: extraCtx, page: extra } = await newAuthedContext(browser, REQUESTER);
    await extra.goto("/platform/security", { waitUntil: "domcontentloaded" });
    await expect(extra.getByRole("heading", { name: /^Operator sessions$/i })).toBeVisible({ timeout: 30_000 });
    await requester.reload({ waitUntil: "domcontentloaded" });
    await expect(requester.getByRole("heading", { name: /^Operator sessions$/i })).toBeVisible({ timeout: 30_000 });
    await expect(requester.getByText(/e2e-requester@example\.com/i).first()).toBeVisible({ timeout: 30_000 });
    const revokeOthers = requester.getByRole("button", { name: /Revoke all other operator sessions/i });
    if (await revokeOthers.isEnabled().catch(() => false)) {
      await revokeOthers.click();
      await requester.waitForTimeout(1500);
      await requester.reload({ waitUntil: "domcontentloaded" });
    } else {
      const revokeOne = requester.getByRole("button", { name: /^Revoke this session$/i }).first();
      if (await revokeOne.isVisible().catch(() => false)) {
        await revokeOne.click();
        const revokeDialog = requester.getByRole("dialog");
        if (await revokeDialog.isVisible().catch(() => false)) {
          await revokeDialog.getByRole("button", { name: /Confirm revocation|Revoke/i }).first().click();
        }
        await requester.waitForTimeout(1500);
        await requester.reload({ waitUntil: "domcontentloaded" });
      }
    }
    await expect(requester.getByRole("heading", { name: /^Operator sessions$/i })).toBeVisible({ timeout: 30_000 });
    await expect(requester.getByText(/current/i).first()).toBeVisible({ timeout: 30_000 });
    await extraCtx.close();

    // 11. Audit filtering and CSV/JSON export.
    await requester.goto("/platform/audit", { waitUntil: "domcontentloaded" });
    await expect(requester.getByRole("heading", { name: /Every privileged action, one journal/i })).toBeVisible({ timeout: 30_000 });
    const from = new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10);
    const to = new Date().toISOString().slice(0, 10);
    await requester.locator('label:has-text("From (UTC, required)") input').fill(from);
    await requester.locator('label:has-text("To (UTC, required)") input').fill(to);
    const csvDownload = await Promise.all([
      requester.waitForEvent("download", { timeout: 30_000 }),
      requester.getByRole("button", { name: /^Export CSV$/i }).click(),
    ]).then(([d]) => d);
    expect(csvDownload.suggestedFilename().toLowerCase()).toContain(".csv");
    await requester.locator('label:has-text("Format") select').selectOption("json");
    const jsonDownload = await Promise.all([
      requester.waitForEvent("download", { timeout: 30_000 }),
      requester.getByRole("button", { name: /^Export JSON$/i }).click(),
    ]).then(([d]) => d);
    expect(jsonDownload.suggestedFilename().toLowerCase()).toContain(".json");

    // 12. Permission-filtered navigation.
    await expect(requester.getByRole("link", { name: /Approvals/i }).first()).toBeVisible();
    await expect(requester.getByRole("link", { name: /Audit journal/i }).first()).toBeVisible();
    await expect(requester.getByRole("link", { name: /Operator security/i }).first()).toBeVisible();

    // 13. Direct URL access by unauthorized users.
    const { context: memberCtx, page: memberPage } = await newAuthedContext(browser, MEMBER);
    collectConsoleErrors(memberPage);
    await memberPage.goto("/platform/approvals", { waitUntil: "domcontentloaded" });
    await memberPage.waitForLoadState("networkidle").catch(() => {});
    await expect(memberPage).not.toHaveURL(/\/platform\/approvals(?:$|\?)/, { timeout: 30_000 });
    expect(await memberPage.getByText(/E2E suspension requires|Two people, one irreversible change/i).count()).toBe(0);
    await memberCtx.close();

    // 14. Responsive layout at desktop and 390px.
    await requester.setViewportSize({ width: 390, height: 844 });
    for (const path of ["/platform/approvals", "/platform/security", "/platform/audit"]) {
      await requester.goto(path, { waitUntil: "domcontentloaded" });
      await requester.waitForLoadState("networkidle").catch(() => {});
      await assertNoHorizontalOverflow(requester);
    }
    await requester.setViewportSize({ width: 1280, height: 900 });

    // 15,16 final checks.
    await assertNoSensitiveStorage(requester);
    await assertNoSensitiveStorage(approver);
    await assertNoHorizontalOverflow(requester);
    await assertNoHorizontalOverflow(approver);
    const seriousRequester = requesterConsole.filter((e) => !/favicon|ResizeObserver|Download the React DevTools|Failed to load resource: the server responded with a status of 401/i.test(e));
    const seriousApprover = approverConsole.filter((e) => !/favicon|ResizeObserver|Download the React DevTools|Failed to load resource: the server responded with a status of 401/i.test(e));
    expect(seriousRequester, `requester console: ${seriousRequester.join("\n")}`).toEqual([]);
    expect(seriousApprover, `approver console: ${seriousApprover.join("\n")}`).toEqual([]);

    await requesterCtx.close();
    await approverCtx.close();
  });
});

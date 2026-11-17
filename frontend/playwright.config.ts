import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3100);
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`;
const ROOT = path.resolve(__dirname, "..");
const E2E_DB = process.env.E2E_DATABASE_URL ?? `sqlite:///${ROOT.replace(/\\/g, "/")}/backend/tmp_e2e_browser.db`;
/**
 * Fernet keys are 32 random bytes encoded as URL-safe base64: 44 characters
 * (43 payload characters plus the "=" pad).
 */
const FERNET_KEY_PATTERN = /^[A-Za-z0-9_-]{43}=$/;

/**
 * The E2E harness needs a disposable test-only Fernet key so the seeded backend
 * can encrypt synthetic TOTP secrets. It is supplied by the developer's shell
 * and is never defaulted, generated, or committed from this file.
 */
function requireE2eMfaKey(): string {
  const key = process.env.E2E_MFA_KEY?.trim() ?? "";
  if (!key) {
    throw new Error(
      "E2E_MFA_KEY is not set. The Playwright suite needs a disposable, test-only\n" +
        "Fernet key for its synthetic MFA accounts and has no default.\n\n" +
        "Generate a throwaway key and export it in the shell that runs the tests:\n" +
        '  export E2E_MFA_KEY="$(python -c \'from cryptography.fernet import Fernet; ' +
        'print(Fernet.generate_key().decode())\')"\n' +
        "  npm run test:e2e\n\n" +
        "Never use a production key here and never commit the value. See the\n" +
        "Testing and verification section of README.md.",
    );
  }
  if (!FERNET_KEY_PATTERN.test(key) || Buffer.from(key, "base64url").length !== 32) {
    throw new Error(
      "E2E_MFA_KEY is not a valid Fernet key (expected 32 bytes as URL-safe base64,\n" +
        "44 characters ending in \"=\"). Generate a fresh disposable key as described\n" +
        "in the Testing and verification section of README.md.",
    );
  }
  return key;
}

const E2E_MFA_KEY = requireE2eMfaKey();

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command:
        process.platform === "win32"
          ? `.venv\\Scripts\\python.exe -m app.scripts.seed_e2e_browser && .venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`
          : `.venv/bin/python -m app.scripts.seed_e2e_browser && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: path.join(ROOT, "backend"),
      url: `${BACKEND_URL}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        ...process.env,
        E2E_DATABASE_URL: E2E_DB,
        E2E_MFA_KEY,
        E2E_RESET: "1",
        DATABASE_URL: E2E_DB,
        ENVIRONMENT: "test",
        MFA_ENCRYPTION_KEY: E2E_MFA_KEY,
        CORS_ORIGINS: FRONTEND_URL,
        NEXT_PUBLIC_API_URL: BACKEND_URL,
      },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT}`,
      cwd: __dirname,
      url: FRONTEND_URL,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: BACKEND_URL,
        API_INTERNAL_URL: BACKEND_URL,
      },
    },
  ],
});

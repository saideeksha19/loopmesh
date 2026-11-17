"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { postJson } from "@/lib/client-api";
import type {
  MfaConfirmation,
  MfaEnrollment,
  MfaStatus,
} from "@/lib/platform-types";

type Action = "regenerate" | "disable" | null;

const INPUT =
  "mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600";
const BUTTON =
  "h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 hover:bg-forest-800 disabled:opacity-50";

/**
 * TOTP enrolment and recovery.
 *
 * The secret and recovery codes exist only in this component's memory for the
 * one response that returns them. They are never written to storage, a cookie
 * or the URL, and a refresh loses them by design.
 */
export function MfaPanel({ status }: { status: MfaStatus }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [enrollment, setEnrollment] = useState<MfaEnrollment | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [verifyCode, setVerifyCode] = useState("");
  const [action, setAction] = useState<Action>(null);
  const [actionPassword, setActionPassword] = useState("");
  const [actionCode, setActionCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const locked = Boolean(status.locked_until && new Date(status.locked_until) > new Date());

  async function beginEnrollment() {
    if (pending || !password) return;
    setPending(true);
    setError(null);
    const result = await postJson<MfaEnrollment>("/auth/mfa/enroll", {
      current_password: password,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setEnrollment(result.data);
    setPassword("");
  }

  async function confirmEnrollment() {
    if (pending || !confirmCode) return;
    setPending(true);
    setError(null);
    const result = await postJson<MfaConfirmation>("/auth/mfa/confirm", {
      code: confirmCode,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setCodes(result.data.recovery_codes);
    setEnrollment(null);
    setConfirmCode("");
    setMessage("Two-factor authentication is active for this operator account.");
    router.refresh();
  }

  async function verifySession() {
    if (pending || !verifyCode) return;
    setPending(true);
    setError(null);
    const result = await postJson<{ verified: boolean }>("/auth/mfa/verify", {
      code: verifyCode,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setVerifyCode("");
    setMessage("This session is verified. Platform capabilities are now available.");
    router.refresh();
  }

  async function submitAction() {
    if (!action || pending || !actionPassword || !actionCode) return;
    setPending(true);
    setError(null);
    const factor = useRecovery
      ? { recovery_code: actionCode.trim() }
      : { code: actionCode.trim() };
    const result = await postJson<{ message: string; recovery_codes?: string[] }>(
      `/auth/mfa/${action === "disable" ? "disable" : "recovery-codes/regenerate"}`,
      { current_password: actionPassword, ...factor },
    );
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setActionPassword("");
    setActionCode("");
    setAction(null);
    if (action === "regenerate") {
      setCodes(result.data.recovery_codes ?? []);
      setMessage("Previous recovery codes no longer work. Store the new set now.");
    } else {
      setMessage("Two-factor authentication was disabled. All of your sessions were revoked.");
    }
    router.refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={status.enrolled ? "forest" : "warning"} mono>
          {status.enrolled ? "TOTP enrolled" : "Not enrolled"}
        </Badge>
        <Badge tone={status.verified ? "forest" : "outline"} mono>
          {status.verified ? "This session verified" : "This session unverified"}
        </Badge>
        {status.recovery_codes_remaining > 0 ? (
          <span className="font-mono text-[9.5px] text-ink-400">
            {status.recovery_codes_remaining} recovery code
            {status.recovery_codes_remaining === 1 ? "" : "s"} remaining
          </span>
        ) : null}
      </div>

      {locked ? (
        <p role="alert" className="rounded-lg border border-rust-500/25 bg-rust-500/[0.06] p-3 text-[11.5px] text-rust-500">
          Verification is temporarily locked after repeated failures. Try again after{" "}
          {new Date(status.locked_until as string).toLocaleString()}.
        </p>
      ) : null}

      {status.enrolled && !status.verified && !locked ? (
        <div className="rounded-lg border border-clay-500/25 bg-clay-500/[0.06] p-3">
          <p className="text-[11.5px] font-medium text-ink-800">
            This session has not presented its second factor.
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-600">
            Platform routes stay closed until a current TOTP code is accepted. The session already
            exists; verification upgrades it rather than issuing a new one.
          </p>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="label-mono text-[8.5px] text-ink-400">Authenticator code</span>
              <input
                value={verifyCode}
                onChange={(event) => setVerifyCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                className={`${INPUT} w-40 font-mono`}
              />
            </label>
            <button type="button" onClick={verifySession} disabled={pending} className={BUTTON}>
              {pending ? "Verifying…" : "Verify session"}
            </button>
          </div>
        </div>
      ) : null}

      {!status.enrolled ? (
        <div>
          <p className="text-[11.5px] leading-relaxed text-ink-600">
            Enrolment needs your current password, then a valid code from the authenticator app.
            LOOPMESH does not send codes by email or SMS and never displays a recovery secret after
            the enrolment response.
          </p>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="label-mono text-[8.5px] text-ink-400">Current password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className={`${INPUT} w-60`}
              />
            </label>
            <button
              type="button"
              onClick={beginEnrollment}
              disabled={pending || !password}
              className={BUTTON}
            >
              {pending ? "Preparing…" : "Begin enrolment"}
            </button>
          </div>
        </div>
      ) : null}

      {enrollment ? (
        <div className="rounded-lg border border-paper-300 bg-paper-50 p-3">
          <p className="text-[11.5px] font-medium text-ink-800">
            Add this secret to an authenticator app, then confirm one code.
          </p>
          <p className="mt-1 text-[10.5px] text-ink-500">
            The secret is shown once for this enrolment. It is encrypted at rest by the API.
          </p>
          <code className="mt-2 block overflow-x-auto rounded border border-paper-300 bg-white p-2 font-mono text-[11px] tracking-wider text-ink-800">
            {enrollment.secret}
          </code>
          <details className="mt-2">
            <summary className="cursor-pointer font-mono text-[9.5px] text-ink-400">
              Provisioning URI
            </summary>
            <code className="mt-1 block overflow-x-auto font-mono text-[10px] break-all text-ink-500">
              {enrollment.provisioning_uri}
            </code>
          </details>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="block">
              <span className="label-mono text-[8.5px] text-ink-400">Six-digit code</span>
              <input
                value={confirmCode}
                onChange={(event) => setConfirmCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                className={`${INPUT} w-40 font-mono`}
              />
            </label>
            <button
              type="button"
              onClick={confirmEnrollment}
              disabled={pending || confirmCode.length < 6}
              className={BUTTON}
            >
              {pending ? "Confirming…" : "Confirm enrolment"}
            </button>
          </div>
        </div>
      ) : null}

      {codes ? (
        <div className="rounded-lg border border-clay-500/30 bg-clay-500/[0.06] p-3">
          <p className="text-[11.5px] font-medium text-ink-800">
            Recovery codes — shown once, never again
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-600">
            Each code works once if the authenticator is unavailable. Store them somewhere safe
            now; refreshing this page discards them and only their hashes remain.
          </p>
          <ul className="mt-2 grid gap-1 font-mono text-[12px] text-ink-800 sm:grid-cols-2">
            {codes.map((code) => (
              <li key={code} className="rounded border border-paper-300 bg-white px-2 py-1">
                {code}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => setCodes(null)}
            className="mt-2 h-8 rounded-lg border border-paper-300 px-3 text-[11px] text-ink-600 hover:bg-paper-100"
          >
            I saved these codes
          </button>
        </div>
      ) : null}

      {status.enrolled ? (
        <div className="border-t border-paper-200 pt-3">
          <p className="text-[11.5px] font-medium text-ink-800">Recovery</p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-500">
            Regenerating recovery codes or disabling MFA requires the current password and a valid
            factor. Disabling revokes all of your sessions and closes platform access.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                setError(null);
                setAction("regenerate");
              }}
              className="h-8 rounded-lg border border-paper-300 px-3 text-[11px] text-ink-600 hover:bg-paper-100"
            >
              Regenerate recovery codes
            </button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setAction("disable");
              }}
              className="h-8 rounded-lg border border-rust-500/30 bg-rust-500/10 px-3 text-[11px] text-rust-500 hover:bg-rust-500/15"
            >
              Disable MFA
            </button>
          </div>

          {action ? (
            <div className="mt-3 rounded-lg border border-paper-300 p-3">
              <p className="text-[11.5px] font-medium text-ink-800">
                {action === "disable" ? "Disable two-factor authentication" : "Regenerate recovery codes"}
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <label className="block">
                  <span className="label-mono text-[8.5px] text-ink-400">Current password</span>
                  <input
                    type="password"
                    value={actionPassword}
                    onChange={(event) => setActionPassword(event.target.value)}
                    autoComplete="current-password"
                    className={INPUT}
                  />
                </label>
                <label className="block">
                  <span className="label-mono text-[8.5px] text-ink-400">
                    {useRecovery ? "Recovery code" : "Authenticator code"}
                  </span>
                  <input
                    value={actionCode}
                    onChange={(event) => setActionCode(event.target.value)}
                    autoComplete="one-time-code"
                    maxLength={64}
                    className={`${INPUT} font-mono`}
                  />
                </label>
              </div>
              <label className="mt-2 flex items-center gap-2 text-[11px] text-ink-600">
                <input
                  type="checkbox"
                  checked={useRecovery}
                  onChange={(event) => setUseRecovery(event.target.checked)}
                />
                Use a single-use recovery code instead
              </label>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={submitAction}
                  disabled={pending || !actionPassword || !actionCode}
                  className="h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 hover:bg-forest-800 disabled:opacity-50"
                >
                  {pending ? "Applying…" : action === "disable" ? "Confirm disable" : "Confirm regenerate"}
                </button>
                <button
                  type="button"
                  onClick={() => setAction(null)}
                  disabled={pending}
                  className="h-9 rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-[11.5px] text-rust-500">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="text-[11.5px] leading-relaxed text-forest-700">
          {message}
        </p>
      ) : null}
    </div>
  );
}

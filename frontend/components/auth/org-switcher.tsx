"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { postJson } from "@/lib/client-api";
import { activeMembership, roleLabel, type SessionUser } from "@/lib/auth";

/**
 * Lists only the memberships the API returned for the signed-in user. The
 * switch itself is authorised server-side; a refused switch leaves the session
 * on its current organisation and reports the reason.
 */
export function OrgSwitcher({ user }: { user: SessionUser }) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const memberships = user.memberships.filter((membership) => membership.status === "active");
  const active = activeMembership(user);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function choose(organizationId: string) {
    if (pendingId) return;
    if (organizationId === active?.organization_id) {
      setOpen(false);
      return;
    }
    setPendingId(organizationId);
    setError(null);
    const result = await postJson<SessionUser>("/auth/switch-organization", {
      organization_id: organizationId,
    });
    setPendingId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setOpen(false);
    router.refresh();
  }

  if (memberships.length <= 1) {
    return (
      <span className="hidden items-center gap-1.5 rounded-full border border-paper-300 bg-paper-50 px-2.5 py-1 text-[10.5px] font-medium text-ink-700 sm:flex">
        <span className="h-1.5 w-1.5 rounded-full bg-forest-600" aria-hidden />
        <span className="max-w-[180px] truncate">
          {active?.organization_name ?? "No organisation"}
        </span>
      </span>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((current) => !current);
          setError(null);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Active organisation: ${active?.organization_name ?? "none"}. Switch organisation`}
        className="flex max-w-[220px] items-center gap-1.5 rounded-full border border-paper-300 bg-paper-50 px-2.5 py-1 text-[10.5px] font-medium text-ink-700 transition-colors hover:border-forest-600/40 hover:bg-white"
      >
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-forest-600" aria-hidden />
        <span className="truncate">{active?.organization_name ?? "Select organisation"}</span>
        <svg viewBox="0 0 12 12" aria-hidden className="h-2.5 w-2.5 shrink-0 text-ink-400" fill="currentColor">
          <path d="M6 8.5 1.8 4.3h8.4L6 8.5Z" />
        </svg>
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Switch organisation"
          className="absolute right-0 z-50 mt-1.5 w-[280px] overflow-hidden rounded-xl border border-paper-200 bg-[#fffdf8] p-1.5 shadow-[0_18px_40px_-24px_rgba(9,26,20,0.45)] animate-fade"
        >
          <p className="label-mono px-2 py-1.5 text-[8.5px] text-ink-400">Your memberships</p>
          {memberships.map((membership) => {
            const current = membership.organization_id === active?.organization_id;
            return (
              <button
                key={membership.id}
                type="button"
                role="menuitemradio"
                aria-checked={current}
                disabled={pendingId !== null}
                onClick={() => void choose(membership.organization_id)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-paper-100 disabled:opacity-60"
              >
                <span
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                    current ? "border-forest-600 bg-forest-600 text-paper-50" : "border-paper-300"
                  }`}
                  aria-hidden
                >
                  {current ? (
                    <svg viewBox="0 0 10 10" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="m2 5.2 2 2 4-4.4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : null}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] text-ink-900">
                    {membership.organization_name ?? membership.organization_id}
                  </span>
                  <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-wider text-ink-400">
                    {roleLabel(membership.role)}
                    {membership.scope !== "organization" ? ` · ${membership.scope}` : ""}
                  </span>
                </span>
                {pendingId === membership.organization_id ? (
                  <span
                    className="h-3 w-3 shrink-0 animate-spin rounded-full border-[1.5px] border-forest-600/30 border-t-forest-600"
                    aria-hidden
                  />
                ) : null}
              </button>
            );
          })}
          {error ? (
            <p role="alert" className="mx-1 mt-1 rounded-md bg-rust-500/[0.08] px-2 py-1.5 text-[11px] leading-relaxed text-rust-500">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

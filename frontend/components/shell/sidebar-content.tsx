"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LoopMark } from "@/components/icons";
import { isActivePath, navGroupsFor } from "@/components/shell/nav-config";

export function SidebarContent({
  apiOnline,
  permissions,
  onNavigate,
}: {
  apiOnline: boolean;
  permissions: string[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const groups = navGroupsFor(permissions);

  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-5 pt-6">
        <Link href="/overview" onClick={onNavigate} className="group flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-lime-400/25 bg-lime-400/10 text-lime-400 shadow-[0_0_0_1px_rgba(198,243,92,0.06),0_12px_30px_-18px_rgba(198,243,92,0.7)] transition-premium group-hover:bg-lime-400/15">
            <LoopMark className="h-6 w-6" />
          </span>
          <span className="min-w-0">
            <span className="block text-[13px] font-semibold tracking-[0.28em] text-paper-50">
              LOOPMESH
            </span>
            <span className="label-mono mt-1 block text-[8.5px] text-ink-400/90 transition-colors group-hover:text-lime-300/80">
              Industrial intelligence OS
            </span>
          </span>
        </Link>
      </div>

      <nav className="flex-1 space-y-7 overflow-y-auto px-3 pb-6">
        {groups.map((group) => (
          <div key={group.label}>
            <p className="label-mono px-2 pb-2.5 text-[8.5px] text-ink-400/70">{group.label}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = isActivePath(pathname, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={[
                        "group relative flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-[12.5px] transition-premium",
                        active
                          ? "bg-white/[0.08] text-paper-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                          : "text-ink-400/80 hover:bg-white/[0.045] hover:text-paper-100",
                      ].join(" ")}
                    >
                      <span
                        className={[
                          "absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full transition-premium",
                          active ? "bg-lime-400 shadow-[0_0_12px_rgba(198,243,92,0.55)]" : "bg-transparent",
                        ].join(" ")}
                      />
                      <Icon
                        className={[
                          "h-[17px] w-[17px] shrink-0 transition-premium",
                          active ? "text-lime-400" : "text-ink-400/70 group-hover:text-paper-200",
                        ].join(" ")}
                      />
                      <span className="truncate">{item.label}</span>
                      {item.phase ? (
                        <span className="ml-auto rounded-md border border-forest-700/80 bg-forest-900/50 px-1.5 py-[1px] font-mono text-[8.5px] tracking-widest text-ink-400/80">
                          {item.phase}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="space-y-3 border-t border-forest-800/80 px-4 py-5">
        <div className="rounded-xl border border-forest-700/70 bg-forest-950/55 p-3 backdrop-blur-sm">
          <p className="label-mono text-[8.5px] text-ink-400/70">Build stage</p>
          <p className="mt-1.5 text-[12px] font-medium text-paper-100">Phase 1 — foundation</p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-400/80">
            Deterministic matching is live. Solver and agents are designed, not enabled.
          </p>
        </div>
        <div className="flex items-center justify-between px-1">
          <span className="flex items-center gap-2 text-[11px] text-ink-400/80">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                apiOnline ? "bg-lime-400 animate-pulse-soft shadow-[0_0_10px_rgba(198,243,92,0.6)]" : "bg-rust-500"
              }`}
            />
            API {apiOnline ? "connected" : "offline"}
          </span>
          <span className="label-mono text-[8.5px] text-ink-400/60">v0.1</span>
        </div>
      </div>
    </div>
  );
}

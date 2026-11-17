"use client";

import { usePathname } from "next/navigation";

import { OrgSwitcher } from "@/components/auth/org-switcher";
import { UserMenu } from "@/components/auth/user-menu";
import { MobileNav } from "@/components/shell/mobile-nav";
import { ALL_NAV_ITEMS } from "@/components/shell/nav-config";
import type { SessionUser } from "@/lib/auth";

export function TopBar({ apiOnline, user }: { apiOnline: boolean; user: SessionUser }) {
  const pathname = usePathname();
  const current =
    ALL_NAV_ITEMS.find((item) =>
      item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
    ) ?? ALL_NAV_ITEMS[0];

  return (
    <header className="sticky top-0 z-30 border-b border-paper-300/60 bg-paper-100/80 backdrop-blur-xl supports-[backdrop-filter]:bg-paper-100/70">
      <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center gap-3 px-5 sm:px-8">
        <MobileNav apiOnline={apiOnline} permissions={user.permissions} />
        <div className="min-w-0">
          <p className="label-mono text-[8.5px] text-ink-400">LOOPMESH · resource intelligence</p>
          <p className="truncate text-[13.5px] font-semibold tracking-[-0.01em] text-ink-900">{current.short}</p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <OrgSwitcher user={user} />
          <span
            className={[
              "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-wider transition-premium sm:flex",
              apiOnline
                ? "border-lime-500/30 bg-lime-400/10 text-forest-800 shadow-[0_0_0_1px_rgba(198,243,92,0.05)]"
                : "border-rust-500/30 bg-rust-500/10 text-rust-500",
            ].join(" ")}
            title={apiOnline ? "The LOOPMESH API is responding" : "The LOOPMESH API is not responding"}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${apiOnline ? "bg-lime-500 shadow-[0_0_8px_rgba(198,243,92,0.7)]" : "bg-rust-500"}`}
            />
            <span className="hidden md:inline">{apiOnline ? "API online" : "API offline"}</span>
          </span>
          <UserMenu user={user} />
        </div>
      </div>
    </header>
  );
}

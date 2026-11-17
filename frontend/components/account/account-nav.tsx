"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ACCOUNT_PASSWORD_PATH, ACCOUNT_SESSIONS_PATH } from "@/lib/auth";

const LINKS = [
  { href: ACCOUNT_PASSWORD_PATH, label: "Password" },
  { href: ACCOUNT_SESSIONS_PATH, label: "Sessions & devices" },
];

export function AccountNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Account security" className="flex flex-wrap items-center gap-1.5">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={[
              "rounded-lg border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide transition-colors",
              active
                ? "border-forest-700/30 bg-forest-800/[0.09] text-forest-700"
                : "border-paper-300 bg-paper-50 text-ink-500 hover:bg-paper-100",
            ].join(" ")}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}

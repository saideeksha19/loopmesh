"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isPlatformActive, platformNavFor } from "@/lib/platform";

/**
 * Platform navigation. Separate from the organisation workspace: it lists only
 * platform capabilities and never shows a tenant's business screens.
 */
export function PlatformNav({ permissions }: { permissions: string[] }) {
  const pathname = usePathname();
  const items = platformNavFor(permissions);

  return (
    <nav
      aria-label="Platform administration"
      className="-mx-1 flex items-center gap-1 overflow-x-auto px-1 pb-2"
    >
      {items.map((item) => {
        const active = isPlatformActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={[
              "shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] transition-colors",
              active
                ? "bg-white/[0.09] text-paper-50"
                : "text-forest-500 hover:bg-white/[0.05] hover:text-paper-200",
            ].join(" ")}
          >
            <span className="hidden sm:inline">{item.label}</span>
            <span className="sm:hidden">{item.short}</span>
          </Link>
        );
      })}
    </nav>
  );
}

import type { ComponentType, SVGProps } from "react";

import {
  AgentIcon,
  LedgerIcon,
  MembersIcon,
  MaterialIcon,
  NetworkIcon,
  OpportunityIcon,
  OptimizationIcon,
  OverviewIcon,
} from "@/components/icons";
import {
  AuditIcon,
  ProposalIcon,
  TransactionIcon,
} from "@/components/workflow/icons";

export type NavItem = {
  href: string;
  label: string;
  short: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  phase?: string;
  /** Capability required to see the entry. Navigation only — the API decides. */
  permission?: string;
};

export type NavGroup = { label: string; items: NavItem[] };

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { href: "/overview", label: "Overview", short: "Overview", icon: OverviewIcon, permission: "dashboard.view" },
      { href: "/materials", label: "Material intelligence", short: "Materials", icon: MaterialIcon, permission: "material.view" },
      { href: "/network", label: "Resource network", short: "Network", icon: NetworkIcon, permission: "network.view" },
      {
        href: "/opportunities",
        label: "Recovery opportunities",
        short: "Opportunities",
        icon: OpportunityIcon,
        permission: "opportunity.view",
      },
      { href: "/proposals", label: "Recovery proposals", short: "Proposals", icon: ProposalIcon, permission: "proposal.view" },
      {
        href: "/transactions",
        label: "Recovery transactions",
        short: "Transactions",
        icon: TransactionIcon,
        permission: "transaction.view",
      },
    ],
  },
  {
    label: "Intelligence",
    items: [
      {
        href: "/optimization",
        label: "Optimization centre",
        short: "Optimization",
        icon: OptimizationIcon,
        phase: "P3",
        permission: "optimization.view",
      },
      {
        href: "/agents",
        label: "Agent control",
        short: "Agents",
        icon: AgentIcon,
        phase: "P2",
        permission: "agent.view",
      },
    ],
  },
  {
    label: "Platform",
    items: [
      {
        href: "/platform",
        label: "Platform administration",
        short: "Platform",
        icon: OptimizationIcon,
        permission: "platform.dashboard.view",
      },
    ],
  },
  {
    label: "Governance",
    items: [
      {
        href: "/members",
        label: "Members & invitations",
        short: "Members",
        icon: MembersIcon,
        permission: "member.view",
      },
      { href: "/ledger", label: "Impact ledger", short: "Ledger", icon: LedgerIcon, permission: "ledger.view" },
      { href: "/audit", label: "Audit journal", short: "Audit", icon: AuditIcon, permission: "audit.view" },
    ],
  },
];

export const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);

/**
 * Navigation reflects the capabilities reported by `/auth/me`. Hiding an entry
 * is presentation only: every route and API call is authorised server-side.
 */
export function navGroupsFor(permissions: string[]): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.permission || permissions.includes(item.permission)),
  })).filter((group) => group.items.length > 0);
}

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/overview") return pathname === "/overview";
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

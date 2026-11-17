import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function LoopMark({ className, ...props }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" fill="none" className={className} {...props}>
      <circle cx="20" cy="20" r="13.5" stroke="currentColor" strokeWidth="1.6" opacity="0.55" />
      <path
        d="M20 6.5a13.5 13.5 0 0 1 0 27"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="20" cy="6.5" r="3" fill="currentColor" />
      <circle cx="31.2" cy="27.5" r="1.9" fill="currentColor" opacity="0.7" />
      <circle cx="8.8" cy="27.5" r="1.9" fill="currentColor" opacity="0.35" />
    </svg>
  );
}

export function OverviewIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 7h6V4h-6z" />
    </svg>
  );
}

export function MaterialIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" />
      <path d="M4 7.5 12 12l8-4.5M12 12v9" />
    </svg>
  );
}

export function NetworkIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="6" cy="7" r="2.6" />
      <circle cx="18" cy="8" r="2.6" />
      <circle cx="12" cy="18" r="2.6" />
      <path d="M8.4 8.2 15.6 7.9M7.3 9.3l3.5 6.5M16.7 10.2l-3.4 5.6" />
    </svg>
  );
}

export function OpportunityIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3v4M12 17v4M4.9 7.5 8.4 9.5M15.6 14.5l3.5 2M19.1 7.5 15.6 9.5M8.4 14.5l-3.5 2" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  );
}

export function OptimizationIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 19V9M9 19V5M14 19v-7M19 19v-4" />
      <path d="M3 19h18" />
    </svg>
  );
}

export function AgentIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="4" y="7" width="16" height="11" rx="2.5" />
      <path d="M9 12h.01M15 12h.01M9.5 15.5h5" />
      <path d="M12 4v3M8 18v2M16 18v2" />
    </svg>
  );
}

export function MembersIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
      <path d="M16 5.4a3 3 0 0 1 0 5.8M17.4 14.4c2 .6 3.4 2.3 3.4 4.6" />
    </svg>
  );
}

export function LedgerIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M5 4h11l3 3v13H5z" />
      <path d="M9 9h6M9 13h6M9 17h4" />
    </svg>
  );
}

export function ArrowRight({ className, ...props }: IconProps) {
  return (
    <svg {...base} className={className} {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export function ArrowUpRight({ className, ...props }: IconProps) {
  return (
    <svg {...base} className={className} {...props}>
      <path d="M7 17 17 7M9 7h8v8" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 16V4M8 8l4-4 4 4" />
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="m5 12.5 4.5 4.5L19 7" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 4 3 20h18z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 8h.01" />
    </svg>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

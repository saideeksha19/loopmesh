import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 h-10 w-10 rounded-full border border-dashed border-paper-300 bg-paper-50" />
      <p className="text-[13px] font-medium text-ink-700">{title}</p>
      <p className="mt-1 max-w-sm text-[12px] leading-relaxed text-ink-400">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

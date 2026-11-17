import { Panel } from "@/components/ui/panel";

/**
 * Rendered when the signed-in platform operator lacks the capability for one
 * console page. Kept deliberately explicit: a missing capability must read as
 * "not permitted", never as "empty data".
 */
export function PlatformDenied({
  title,
  capability,
  description,
}: {
  title: string;
  capability: string;
  description: string;
}) {
  return (
    <Panel className="p-5 sm:p-6">
      <p className="label-mono text-[9px] text-ink-400">Capability required</p>
      <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">{title}</h2>
      <p className="mt-1.5 max-w-xl text-[12.5px] leading-relaxed text-ink-500">{description}</p>
      <p className="mt-3 inline-flex rounded border border-paper-300 bg-paper-50 px-2 py-1 font-mono text-[10px] text-ink-500">
        {capability}
      </p>
    </Panel>
  );
}

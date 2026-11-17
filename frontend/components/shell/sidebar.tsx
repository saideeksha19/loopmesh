import { SidebarContent } from "@/components/shell/sidebar-content";

export function Sidebar({
  apiOnline,
  permissions,
}: {
  apiOnline: boolean;
  permissions: string[];
}) {
  return (
    <aside className="sticky top-0 hidden h-screen w-[272px] shrink-0 overflow-hidden border-r border-forest-800/70 bg-forest-900 lg:block">
      <div className="tech-grid-dark pointer-events-none absolute inset-0 opacity-35" aria-hidden />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-lime-400/[0.08] to-transparent" aria-hidden />
      <div className="pointer-events-none absolute -left-20 bottom-10 h-56 w-56 rounded-full bg-lime-400/10 blur-3xl" aria-hidden />
      <div className="relative h-full">
        <SidebarContent apiOnline={apiOnline} permissions={permissions} />
      </div>
    </aside>
  );
}

import { MaterialsWorkspace } from "@/components/materials/materials-workspace";
import { MaterialIcon } from "@/components/icons";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { DemoNotice } from "@/components/ui/demo-notice";
import { PageHeader } from "@/components/ui/page-header";
import { apiGet } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { loadSession } from "@/lib/session";
import type { MaterialSummary, OrganizationSummary, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function MaterialsPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string }>;
}) {
  const params = await searchParams;
  const [materials, organizations, session] = await Promise.all([
    apiGet<Page<MaterialSummary>>("/materials?page_size=200"),
    apiGet<Page<OrganizationSummary>>("/organizations?page_size=200"),
    loadSession(),
  ]);
  const failure = materials.ok ? (organizations.ok ? null : organizations.error) : materials.error;

  const memberOrganizationIds =
    session.status === "authenticated"
      ? new Set(
          session.user.memberships
            .filter((membership) => membership.status === "active")
            .map((membership) => membership.organization_id),
        )
      : null;

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Material DNA · structured intelligence"
        title="Material intelligence"
        description="Every stream carries a measured profile: category, quantity, condition, contamination, handling and availability. Profiles arrive through forms, CSV files or specification documents — never from cameras."
        actions={
          <span className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-mono text-[10px] text-paper-100/85">
            <MaterialIcon className="h-3.5 w-3.5" />
            {materials.ok ? `${materials.data.total} streams` : "API offline"}
          </span>
        }
      />

      <div className="mb-4">
        <DemoNotice compact />
      </div>

      {!failure && materials.ok && organizations.ok ? (
        <MaterialsWorkspace
          initialMaterials={materials.data.items}
          organizations={organizations.data.items.filter(
            (organization) => !memberOrganizationIds || memberOrganizationIds.has(organization.id),
          )}
          initialCategory={params.category}
          canCreate={hasPermission(session.status === "authenticated" ? session.user : null, "material.create")}
          canImport={hasPermission(session.status === "authenticated" ? session.user : null, "material.import")}
        />
      ) : (
        <DataUnavailable message={failure ?? undefined} title="Material inventory unavailable" />
      )}
    </>
  );
}

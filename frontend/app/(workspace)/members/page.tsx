import type { Metadata } from "next";

import { InviteMemberForm } from "@/components/invitations/invite-form";
import { InvitationTable } from "@/components/invitations/invitation-table";
import { MemberRoster } from "@/components/members/member-roster";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { type Invitation, type Member, invitableRoles } from "@/lib/account-types";
import { loadSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Members & invitations",
  description:
    "Review the organisation roster, change roles, deactivate members and manage invitations.",
  robots: { index: false, follow: false },
};

export default async function MembersPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const user = state.user;
  const organizationId = user.active_organization_id;
  const organizationName =
    user.memberships.find((membership) => membership.organization_id === organizationId)
      ?.organization_name ?? null;

  const canViewMembers = hasPermission(user, "member.view");
  const canManageMembers = user.is_platform_admin || hasPermission(user, "member.manage");
  const canInvite = user.is_platform_admin || hasPermission(user, "invitation.manage");

  const header = (
    <PageHeader
      cinematic
      eyebrow="Governance · membership"
      title="Who can act, and on what."
      description="The roster is the authoritative record of who belongs to this organisation. Role changes apply to the member's next request, deactivation revokes the sessions opened for this organisation, and a password reset re-arms the forced-rotation gate."
    />
  );

  if (!organizationId) {
    return (
      <>
        {header}
        <Panel className="p-5 sm:p-6">
          <p className="text-[13px] font-medium text-ink-900">Select an organisation first</p>
          <p className="mt-1.5 max-w-xl text-[12px] leading-relaxed text-ink-500">
            Memberships are scoped to one organisation. Use the organisation switcher to choose which roster you are administering.
          </p>
        </Panel>
      </>
    );
  }

  if (!canViewMembers && !canInvite) {
    return (
      <>
        {header}
        <Panel className="p-5 sm:p-6">
          <p className="text-[13px] font-medium text-ink-900">Member administration needs a higher role</p>
          <p className="mt-1.5 max-w-xl text-[12px] leading-relaxed text-ink-500">
            Your role can use the workspace but not read the member register or invite colleagues. Ask an organisation administrator for access. The API enforces the same rule, so this page never receives data it should not show.
          </p>
        </Panel>
      </>
    );
  }

  const roster = canViewMembers
    ? await apiGet<Page<Member>>("/organizations/members?page_size=200")
    : null;

  const invitations = canInvite
    ? await apiGet<Invitation[]>("/auth/invitations?limit=100")
    : null;

  const roles = invitableRoles(user.permissions).map((role) => ({
    value: role.value,
    label: role.label,
  }));

  return (
    <>
      {header}

      <div className="space-y-4">
        {canViewMembers ? (
          <Panel>
            <PanelHeader
              eyebrow="Roster"
              title="Organisation members"
              subtitle={`Everyone with a membership in ${organizationName ?? "this organisation"}. Deactivated memberships are listed for audit and can be reactivated.`}
            />
            {roster && roster.ok ? (
              <MemberRoster initial={roster.data.items} canManage={canManageMembers} />
            ) : (
              <div className="px-5 py-4 sm:px-6">
                <DataUnavailable
                  message={roster?.ok ? "The member register could not be read." : roster?.error}
                  title="Members unavailable"
                />
              </div>
            )}
          </Panel>
        ) : null}

        {canInvite ? (
          <>
            <Panel>
              <PanelHeader
                eyebrow="New invitation"
                title="Invite a colleague"
                subtitle={`The invitation names ${organizationName ?? "your organisation"}, the role you choose and an expiry. The invited person sets their own password.`}
              />
              <InviteMemberForm
                organizationId={organizationId}
                organizationName={organizationName}
                roles={roles}
              />
            </Panel>

            <Panel>
              <PanelHeader
                eyebrow="Register"
                title="Pending invitations"
                subtitle="Revoking an invitation invalidates its link immediately. Accepted, expired and revoked invitations are kept for audit."
              />
              {invitations && invitations.ok ? (
                <InvitationTable initial={invitations.data} />
              ) : (
                <div className="px-5 py-4 sm:px-6">
                  <DataUnavailable
                    message={invitations?.ok ? "The invitation register could not be read." : invitations?.error}
                    title="Invitations unavailable"
                  />
                </div>
              )}
            </Panel>
          </>
        ) : (
          <Panel className="p-5 sm:p-6">
            <p className="text-[13px] font-medium text-ink-900">Invitations need a higher role</p>
            <p className="mt-1.5 max-w-xl text-[12px] leading-relaxed text-ink-500">
              You can read the roster but not invite colleagues. An organisation administrator can grant the invitation capability; the API refuses invitation management without it.
            </p>
          </Panel>
        )}
      </div>

      <p className="mt-4 text-[11px] leading-relaxed text-ink-400">
        Every change here is audited with the actor, the affected member and the previous and new role. Membership deactivation is organisation-scoped: the member&apos;s account and any memberships in other organisations are untouched. Invitation tokens are stored only as hashes, and a password reset never creates, shows or emails a password.
      </p>
    </>
  );
}

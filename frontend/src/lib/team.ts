/**
 * Team member API helpers. Mirrors backend/app/api/routes/team.py.
 */
import { apiFetch } from "@/lib/api";
import type { TeamMember, TeamRole } from "@/types";

export function listTeamMembers(businessId: string, token: string): Promise<TeamMember[]> {
  return apiFetch(`/businesses/${businessId}/team`, { authToken: token });
}

export function inviteTeamMember(
  businessId: string,
  input: { email: string; role: TeamRole },
  token: string
): Promise<TeamMember> {
  return apiFetch(`/businesses/${businessId}/team`, {
    method: "POST",
    authToken: token,
    body: JSON.stringify(input),
  });
}

export function updateTeamMemberRole(
  businessId: string,
  memberId: string,
  role: TeamRole,
  token: string
): Promise<TeamMember> {
  return apiFetch(`/businesses/${businessId}/team/${memberId}`, {
    method: "PATCH",
    authToken: token,
    body: JSON.stringify({ role }),
  });
}

export function removeTeamMember(businessId: string, memberId: string, token: string): Promise<void> {
  return apiFetch(`/businesses/${businessId}/team/${memberId}`, {
    method: "DELETE",
    authToken: token,
  });
}

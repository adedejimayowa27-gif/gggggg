/**
 * Role checks for the UI (Step 12, Batch 12.4).
 *
 * Mirrors the backend's role order (viewer < member < admin < owner; see
 * ROLE_ORDER in backend/app/models/team_member.py) and the table in
 * docs/API.md, "Roles and permissions":
 *
 *   viewer  read-only (plus the what-if preview and the AI assistant)
 *   member  + import data, run syncs, manage alerts, save/delete simulations,
 *           add/edit branches
 *   admin   + set up integrations, manage the team, delete branches, billing
 *   owner   everything
 *
 * Hiding a button here is a convenience so people aren't shown actions they
 * can't use. It is NOT the security boundary: the backend checks the role on
 * every request regardless of what the page shows.
 */
import type { TeamRole } from "@/types";

const ROLE_RANK: Record<TeamRole, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

/**
 * True when `role` is at least `minimum`. A `null` role (still loading, or
 * not found) has no permissions, so controls stay hidden until the role is
 * known rather than flashing on and then disappearing.
 */
export function hasRole(role: TeamRole | null, minimum: TeamRole): boolean {
  return role !== null && ROLE_RANK[role] >= ROLE_RANK[minimum];
}

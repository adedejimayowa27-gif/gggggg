"use client";

/**
 * Team management page (frontend for Step 10, Batch 10.2's backend --
 * app/api/routes/team.py existed with no UI calling it until now).
 *
 * Viewing the team requires only membership; inviting/changing a role/
 * removing someone requires "admin"+ -- mirrored here from
 * currentUserRole so a "member"/"viewer" sees a read-only list instead
 * of controls that would just 404 on click. The backend re-checks this
 * itself on every request regardless (see require_business_role) -- this
 * is UX, not the security boundary.
 */
import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { inviteTeamMember, listTeamMembers, removeTeamMember, updateTeamMemberRole } from "@/lib/team";
import type { TeamMember, TeamRole } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./team.module.css";

const ROLES: TeamRole[] = ["admin", "member", "viewer"];

export default function TeamPage() {
  const { token, user } = useAuth();
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();

  const [members, setMembers] = useState<TeamMember[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TeamRole>("member");
  const [isInviting, setIsInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  const canManage = currentUserRole === "owner" || currentUserRole === "admin";

  const load = () => {
    if (!token || !primaryBusiness) return;
    setIsLoading(true);
    setError(null);
    listTeamMembers(primaryBusiness.id, token)
      .then(setMembers)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the team."))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [token, primaryBusiness]);

  const handleInvite = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !primaryBusiness || !inviteEmail.trim()) return;
    setIsInviting(true);
    setInviteError(null);
    try {
      await inviteTeamMember(primaryBusiness.id, { email: inviteEmail.trim(), role: inviteRole }, token);
      setInviteEmail("");
      setInviteRole("member");
      load();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Could not send the invite.");
    } finally {
      setIsInviting(false);
    }
  };

  const handleRoleChange = async (member: TeamMember, role: TeamRole) => {
    if (!token || !primaryBusiness) return;
    try {
      await updateTeamMemberRole(primaryBusiness.id, member.id, role, token);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update that member's role.");
    }
  };

  const handleRemove = async (member: TeamMember) => {
    if (!token || !primaryBusiness) return;
    if (!window.confirm(`Remove ${member.invited_email} from this business?`)) return;
    try {
      await removeTeamMember(primaryBusiness.id, member.id, token);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove that member.");
    }
  };

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return (
      <ComingSoon title="Team" description="Create a business to start inviting team members." />
    );
  }

  return (
    <div>
      <div className={styles.header}>
        <h1>Team</h1>
      </div>

      {canManage && (
        <form className={styles.inviteForm} onSubmit={handleInvite}>
          <input
            type="email"
            placeholder="colleague@example.com"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            required
            className={styles.input}
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as TeamRole)}
            className={styles.select}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <button type="submit" disabled={isInviting} className={styles.button}>
            {isInviting ? "Inviting…" : "Invite"}
          </button>
        </form>
      )}
      {inviteError && <p className={styles.error}>{inviteError}</p>}

      {error && <p className={styles.error}>{error}</p>}
      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : (
        <div className={styles.list}>
          {members.map((member) => {
            const isSelf = member.user_id === user?.id;
            return (
              <div key={member.id} className={styles.row}>
                <div className={styles.rowLeft}>
                  <span className={styles.email}>{member.invited_email}</span>
                  <span className={styles.status}>{member.status}{isSelf ? " · you" : ""}</span>
                </div>
                <div className={styles.rowRight}>
                  {canManage && member.role !== "owner" ? (
                    <select
                      value={member.role}
                      onChange={(e) => handleRoleChange(member, e.target.value as TeamRole)}
                      className={styles.select}
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className={styles.roleBadge}>{member.role}</span>
                  )}
                  {canManage && member.role !== "owner" && !isSelf && (
                    <button onClick={() => handleRemove(member)} className={styles.removeButton}>
                      Remove
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {members.length === 0 && <p style={{ color: "var(--muted)" }}>No team members yet.</p>}
        </div>
      )}
    </div>
  );
}

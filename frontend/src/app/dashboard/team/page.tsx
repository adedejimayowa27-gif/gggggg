"use client";

/**
 * Team management page.
 *
 * Viewing the team requires only membership; inviting/changing a role/
 * removing someone requires "admin"+ -- mirrored here from
 * currentUserRole so a "member"/"viewer" sees a read-only list instead
 * of controls that would just 404 on click. The backend re-checks this
 * itself on every request regardless (see require_business_role) -- this
 * is UX, not the security boundary.
 *
 * Reform pass -- both visual and operational:
 * - Tokens instead of hardcoded hex, the gold-contrast bug fixed here
 *   too, a colored initial avatar per member (same idea as
 *   TopProductsPanel's colored avatars), status shown as a badge
 *   (active/pending) instead of plain muted text.
 * - Removing a member used window.confirm() -- a native browser dialog
 *   that looks and feels nothing like the rest of the app. Replaced with
 *   the same inline "click again to confirm" pattern used in the
 *   Simulator's delete, for one consistent removal pattern app-wide.
 * - Inviting someone now shows a confirming message ("Invite sent to
 *   x@y.com") instead of silently clearing the field with no feedback
 *   that anything happened.
 */
import { FormEvent, useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { inviteTeamMember, listTeamMembers, removeTeamMember, updateTeamMemberRole } from "@/lib/team";
import type { TeamMember, TeamRole } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./team.module.css";

const ROLES: TeamRole[] = ["admin", "member", "viewer"];

const AVATAR_ACCENTS = ["avatarGold", "avatarLeaf", "avatarPurple", "avatarBlue"] as const;

/** A stable-per-person accent so the same member's avatar color doesn't
 * shift between reloads just because the list happened to re-sort --
 * derived from the email itself, not list position. */
function avatarAccentFor(email: string): (typeof AVATAR_ACCENTS)[number] {
  let hash = 0;
  for (let i = 0; i < email.length; i++) hash = (hash * 31 + email.charCodeAt(i)) >>> 0;
  return AVATAR_ACCENTS[hash % AVATAR_ACCENTS.length];
}

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
  const [inviteFeedback, setInviteFeedback] = useState<string | null>(null);

  // Same armed-then-confirm delete pattern as the Simulator: first click
  // arms this id, a second click within the window actually removes.
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const confirmTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  useEffect(() => {
    return () => {
      if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current);
    };
  }, []);

  const handleInvite = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !primaryBusiness || !inviteEmail.trim()) return;
    setIsInviting(true);
    setInviteError(null);
    setInviteFeedback(null);
    try {
      const sentTo = inviteEmail.trim();
      const created = await inviteTeamMember(primaryBusiness.id, { email: sentTo, role: inviteRole }, token);
      setInviteEmail("");
      setInviteRole("member");
      // The invite itself always succeeds independent of email delivery
      // (see backend/app/services/team.py) -- so a failed send still
      // needs to reach the inviter, or they'll assume the invitee got a
      // link that never arrived.
      setInviteFeedback(
        created.email_sent === false
          ? `${sentTo} was added, but the invite email couldn't be sent -- share the signup link with them directly.`
          : `Invite sent to ${sentTo}.`
      );
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

  const handleRemoveClick = (member: TeamMember) => {
    if (confirmRemoveId !== member.id) {
      setConfirmRemoveId(member.id);
      if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current);
      confirmTimeoutRef.current = setTimeout(() => setConfirmRemoveId(null), 3000);
      return;
    }
    if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current);
    setConfirmRemoveId(null);
    if (!token || !primaryBusiness) return;
    removeTeamMember(primaryBusiness.id, member.id, token)
      .then(load)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not remove that member."));
  };

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Team" description="Create a business to start inviting team members." />;
  }

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Team</h1>
          <p className={styles.subtitle}>Who has access to this business, and what they can do.</p>
        </div>
      </div>

      {canManage && (
        <div className={styles.inviteCard}>
          <div className={styles.cardHeader}>
            <div className={styles.iconWrap}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <h2 className={styles.cardTitle}>Invite someone</h2>
              <p className={styles.cardDescription}>They&rsquo;ll get access once they accept</p>
            </div>
          </div>
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
          {inviteFeedback && <p className={styles.feedback}>{inviteFeedback}</p>}
          {inviteError && <p className={styles.error}>{inviteError}</p>}
        </div>
      )}

      {error && <p className={styles.error}>{error}</p>}

      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : members.length === 0 ? (
        <div className={styles.emptyState}>No team members yet.</div>
      ) : (
        <div className={styles.list}>
          {members.map((member) => {
            const isSelf = member.user_id === user?.id;
            const initial = member.invited_email.trim().charAt(0).toUpperCase() || "?";
            const accent = avatarAccentFor(member.invited_email);
            return (
              <div key={member.id} className={styles.row}>
                <div className={styles.rowLeft}>
                  <span className={`${styles.avatar} ${styles[accent]}`}>{initial}</span>
                  <div className={styles.identity}>
                    <span className={styles.email}>
                      {member.invited_email}
                      {isSelf && <span className={styles.youTag}>you</span>}
                    </span>
                    <span
                      className={`${styles.statusBadge} ${
                        member.status === "active" ? styles.statusActive : styles.statusPending
                      }`}
                    >
                      {member.status}
                    </span>
                  </div>
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
                    <span className={`${styles.roleBadge} ${member.role === "owner" ? styles.roleOwner : ""}`}>
                      {member.role}
                    </span>
                  )}
                  {canManage && member.role !== "owner" && !isSelf && (
                    <button
                      onClick={() => handleRemoveClick(member)}
                      className={`${styles.removeButton} ${
                        confirmRemoveId === member.id ? styles.removeButtonConfirm : ""
                      }`}
                    >
                      {confirmRemoveId === member.id ? "Confirm?" : "Remove"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

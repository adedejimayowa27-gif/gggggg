"use client";

/**
 * Account page (Step 12, Batch 12.5) -- export/delete your own data.
 *
 * This is deliberately its own page, not folded into
 * /dashboard/settings: that page is business-scoped configuration
 * (integrations, branches -- see its own file), while exporting or
 * deleting your account is account-scoped and has nothing to do with
 * whichever business happens to be selected. Reachable from the
 * account menu in DashboardTopbar, next to Log out.
 */
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";
import { deleteMyAccount, exportMyData } from "@/lib/account";
import TwoFactorSettings from "@/components/TwoFactorSettings";
import styles from "./account.module.css";

export default function AccountPage() {
  const { user, token, logout } = useAuth();
  const router = useRouter();

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const [password, setPassword] = useState("");
  const [confirmStep, setConfirmStep] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [blockers, setBlockers] = useState<string | null>(null);

  const handleExport = async () => {
    if (!token) return;
    setIsExporting(true);
    setExportError(null);
    try {
      await exportMyData(token);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Could not export your data.");
    } finally {
      setIsExporting(false);
    }
  };

  const handleDelete = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;

    // Same "click again to confirm" pattern used for removing a team
    // member (see app/dashboard/team/page.tsx) -- except here the
    // second click is a real form submit, since a password is
    // required either way.
    if (!confirmStep) {
      setConfirmStep(true);
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);
    setBlockers(null);
    try {
      await deleteMyAccount(password, token);
      // The account (and its refresh tokens) no longer exist server-side
      // -- logout() tolerates that failure and still clears the local
      // session and redirects, same as a normal logout.
      await logout();
      router.push("/login");
    } catch (err) {
      if (err instanceof ApiError && err.code === "account_owns_shared_businesses") {
        setBlockers(err.message);
      } else {
        setDeleteError(err instanceof ApiError ? err.message : "Could not delete your account.");
      }
      setConfirmStep(false);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Account</h1>
          <p className={styles.subtitle}>{user?.email}</p>
        </div>
      </div>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Export your data</h2>
        <p className={styles.cardDescription}>
          Download a JSON file with your profile, the businesses you own, your team memberships
          elsewhere, and your recent account activity.
        </p>
        <div className={styles.row}>
          <button className={styles.primaryButton} onClick={handleExport} disabled={isExporting}>
            {isExporting ? "Preparing…" : "Export my data"}
          </button>
        </div>
        {exportError && <p className={styles.error}>{exportError}</p>}
      </div>

      <TwoFactorSettings />

      <div className={styles.dangerCard}>
        <h2 className={styles.cardTitle}>Delete your account</h2>
        <p className={styles.cardDescription}>
          This permanently deletes your account and every business you own, along with its
          transactions, branches, integrations, and history. This can&rsquo;t be undone.
        </p>
        <form onSubmit={handleDelete}>
          <input
            type="password"
            placeholder="Confirm your password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setConfirmStep(false);
            }}
            required
            className={styles.input}
          />
          <div className={styles.row}>
            <button
              type="submit"
              className={confirmStep ? styles.dangerButtonConfirm : styles.dangerButton}
              disabled={isDeleting || !password}
            >
              {isDeleting
                ? "Deleting…"
                : confirmStep
                ? "Click again to permanently delete"
                : "Delete my account"}
            </button>
          </div>
        </form>
        {deleteError && <p className={styles.error}>{deleteError}</p>}
        {blockers && <p className={styles.notice}>{blockers}</p>}
      </div>
    </div>
  );
}

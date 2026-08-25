"use client";

import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import styles from "./DashboardTopbar.module.css";

interface Props {
  onMenuToggle: () => void;
}

export default function DashboardTopbar({ onMenuToggle }: Props) {
  const { user, logout } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();

  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <button
          className={styles.menuButton}
          onClick={onMenuToggle}
          aria-label="Toggle navigation menu"
        >
          <span className={styles.menuIcon} />
        </button>

        <div className={styles.businessName}>
          {isLoadingBusinesses ? (
            <span className={styles.placeholder}>Loading…</span>
          ) : primaryBusiness ? (
            primaryBusiness.name
          ) : (
            <span className={styles.placeholder}>No business yet</span>
          )}
        </div>
      </div>

      <div className={styles.right}>
        <span className={styles.userEmail}>{user?.email}</span>
        <button className={styles.logoutButton} onClick={() => logout()}>
          Log out
        </button>
      </div>
    </header>
  );
}

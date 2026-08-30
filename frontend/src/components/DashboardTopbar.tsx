"use client";

import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import styles from "./DashboardTopbar.module.css";

interface Props {
  onMenuToggle: () => void;
}

export default function DashboardTopbar({ onMenuToggle }: Props) {
  const { user, logout } = useAuth();
  const { businesses, primaryBusiness, isLoadingBusinesses, selectBusiness } = useDashboard();

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

        {isLoadingBusinesses ? (
          <span className={styles.placeholder}>Loading…</span>
        ) : !primaryBusiness ? (
          <span className={styles.placeholder}>No business yet</span>
        ) : businesses.length > 1 ? (
          <select
            className={styles.businessSwitcher}
            value={primaryBusiness.id}
            onChange={(e) => selectBusiness(e.target.value)}
            aria-label="Switch business"
          >
            {businesses.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        ) : (
          <div className={styles.businessName}>{primaryBusiness.name}</div>
        )}
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

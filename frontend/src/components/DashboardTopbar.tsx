"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { useClickOutside } from "@/hooks/useClickOutside";
import { listAlerts } from "@/lib/alerts";
import InstallAppButton from "@/components/InstallAppButton";
import type { AlertListItem } from "@/types";
import styles from "./DashboardTopbar.module.css";

interface Props {
  onMenuToggle: () => void;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

const SEVERITY_LABEL: Record<string, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
};

export default function DashboardTopbar({ onMenuToggle }: Props) {
  const { user, token, logout } = useAuth();
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const router = useRouter();

  const [searchValue, setSearchValue] = useState("");

  const [unreadAlerts, setUnreadAlerts] = useState<AlertListItem[]>([]);
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);
  useClickOutside(notifRef, isNotifOpen, () => setIsNotifOpen(false));

  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const helpRef = useRef<HTMLDivElement>(null);
  useClickOutside(helpRef, isHelpOpen, () => setIsHelpOpen(false));

  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  useClickOutside(userMenuRef, isUserMenuOpen, () => setIsUserMenuOpen(false));

  // Real unread alerts (existing Alerts feature), not fabricated
  // notification content -- this is the same data the Alerts page
  // itself shows, just previewed here. Silent on failure: a
  // notifications badge that's briefly wrong/missing is a much smaller
  // problem than an error banner in the middle of the header.
  useEffect(() => {
    if (!primaryBusiness || !token) return;
    listAlerts(primaryBusiness.id, token, "unread")
      .then(setUnreadAlerts)
      .catch(() => setUnreadAlerts([]));
  }, [primaryBusiness, token]);

  const handleSearchSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = searchValue.trim();
    if (trimmed) {
      router.push(`/dashboard/transactions?q=${encodeURIComponent(trimmed)}`);
    }
  };

  const greetingName = primaryBusiness?.name ?? "there";

  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <button className={styles.menuButton} onClick={onMenuToggle} aria-label="Toggle navigation menu">
          <span className={styles.menuIcon} />
        </button>

        {!isLoadingBusinesses && (
          <div>
            <h1 className={styles.greeting}>
              {getGreeting()}, {greetingName} 👋
            </h1>
            <p className={styles.subtitle}>Here&apos;s what&apos;s happening with your business today.</p>
          </div>
        )}
      </div>

      <div className={styles.right}>
        <form className={styles.searchForm} onSubmit={handleSearchSubmit} role="search">
          <svg className={styles.searchIcon} viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <circle cx="9" cy="9" r="6" />
            <path d="M17 17L13.5 13.5" />
          </svg>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search transactions, products…"
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            aria-label="Search"
          />
        </form>

        <div className={styles.iconButtonWrap} ref={notifRef}>
          <button
            className={styles.iconButton}
            onClick={() => setIsNotifOpen((open) => !open)}
            aria-label="Notifications"
            aria-expanded={isNotifOpen}
            title="Notifications"
          >
            <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 12A6 6 0 0 1 16 12" />
              <path d="M3 12H17" />
              <path d="M8 15.5H12" />
            </svg>
            {unreadAlerts.length > 0 && <span className={styles.badge}>{unreadAlerts.length}</span>}
          </button>
          {isNotifOpen && (
            <div className={styles.dropdown}>
              <p className={styles.dropdownTitle}>Notifications</p>
              {unreadAlerts.length === 0 ? (
                <p className={styles.dropdownEmpty}>You&apos;re all caught up.</p>
              ) : (
                <ul className={styles.notifList}>
                  {unreadAlerts.slice(0, 5).map((alert) => (
                    <li key={alert.id} className={styles.notifItem}>
                      <span className={`${styles.notifDot} ${styles[`sev_${alert.severity.toLowerCase()}`] ?? ""}`} />
                      <div>
                        <p className={styles.notifItemTitle}>{alert.title}</p>
                        <p className={styles.notifItemMeta}>{SEVERITY_LABEL[alert.severity] ?? alert.severity}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <a href="/dashboard/alerts" className={styles.dropdownFooterLink}>
                View all alerts
              </a>
            </div>
          )}
        </div>

        <div className={styles.iconButtonWrap} ref={helpRef}>
          <button
            className={styles.iconButton}
            onClick={() => setIsHelpOpen((open) => !open)}
            aria-label="Help"
            aria-expanded={isHelpOpen}
            title="Help"
          >
            <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="10" cy="10" r="7.5" />
              <path d="M7.8 7.8a2.2 2.2 0 1 1 3.3 1.9c-.9.5-1.1.9-1.1 1.8" />
              <circle cx="10" cy="14" r="0.15" fill="currentColor" />
            </svg>
          </button>
          {isHelpOpen && (
            <div className={`${styles.dropdown} ${styles.helpDropdown}`}>
              <p className={styles.dropdownTitle}>Need a hand?</p>
              <p className={styles.helpText}>
                Reach out any time and we&apos;ll get back to you as soon as we can.
              </p>
              <a href="mailto:support@mayorcity.com" className={styles.dropdownFooterLink}>
                support@mayorcity.com
              </a>
            </div>
          )}
        </div>

        <InstallAppButton className={styles.installButton} />

        <div className={styles.userMenuWrap} ref={userMenuRef}>
          <button
            className={styles.avatarButton}
            onClick={() => setIsUserMenuOpen((open) => !open)}
            aria-expanded={isUserMenuOpen}
            aria-label="Account menu"
          >
            <span className={styles.avatar}>{(user?.email ?? "?").charAt(0).toUpperCase()}</span>
          </button>
          {isUserMenuOpen && (
            <div className={styles.dropdown}>
              <p className={styles.userEmailInMenu}>{user?.email}</p>
              <Link
                href="/dashboard/account"
                className={styles.logoutButton}
                style={{ display: "block" }}
                onClick={() => setIsUserMenuOpen(false)}
              >
                Account
              </Link>
              <button className={styles.logoutButton} onClick={() => logout()}>
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

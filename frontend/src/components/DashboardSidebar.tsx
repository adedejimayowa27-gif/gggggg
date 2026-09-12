"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "@/components/Logo";
import NavIcon, { NavIconName } from "@/components/NavIcon";
import { useDashboard } from "@/context/DashboardContext";
import styles from "./DashboardSidebar.module.css";

interface NavItem {
  label: string;
  href: string;
  icon: NavIconName;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

// Grouped to match how these are actually used: MAIN is the day-to-day
// data (unchanged routes/functionality, just regrouped + given icons),
// INTELLIGENCE is the forward-looking tools, BUSINESS is account/team
// administration, SYSTEM is account-level configuration.
const NAV_GROUPS: NavGroup[] = [
  {
    label: "Main",
    items: [
      { label: "Overview", href: "/dashboard", icon: "overview" },
      { label: "Transactions", href: "/dashboard/transactions", icon: "transactions" },
      { label: "Products", href: "/dashboard/products", icon: "products" },
      { label: "Analytics", href: "/dashboard/analytics", icon: "analytics" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { label: "AI Assistant", href: "/dashboard/ai-assistant", icon: "ai" },
      { label: "Simulator", href: "/dashboard/simulator", icon: "simulator" },
      { label: "Alerts", href: "/dashboard/alerts", icon: "alerts" },
    ],
  },
  {
    label: "Business",
    items: [
      { label: "Team", href: "/dashboard/team", icon: "team" },
      { label: "Billing", href: "/dashboard/billing", icon: "billing" },
      { label: "Audit Log", href: "/dashboard/audit-log", icon: "audit-log" },
    ],
  },
  {
    label: "System",
    items: [{ label: "Settings", href: "/dashboard/settings", icon: "settings" }],
  },
];

const COLLAPSE_STORAGE_KEY = "bizintel:sidebarCollapsed";

interface Props {
  onNavigate?: () => void;
  /** The mobile drawer reuses this same component -- forces it to
   * ignore the desktop collapse preference there, since a slim
   * icon-only rail makes no sense inside an already-narrow drawer
   * panel the person just opened specifically to see full labels. */
  forceExpanded?: boolean;
}

export default function DashboardSidebar({ onNavigate, forceExpanded = false }: Props) {
  const pathname = usePathname();
  const { businesses, primaryBusiness, selectBusiness } = useDashboard();
  const [storedCollapsed, setStoredCollapsed] = useState(false);
  const isCollapsed = forceExpanded ? false : storedCollapsed;
  const [isSwitcherOpen, setIsSwitcherOpen] = useState(false);
  const switcherRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isSwitcherOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (switcherRef.current && !switcherRef.current.contains(event.target as Node)) {
        setIsSwitcherOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isSwitcherOpen]);

  // Collapse is a pure display preference (no functionality behind it
  // changes) -- persisted so it survives a reload, same as any other
  // "how I like my UI" setting.
  useEffect(() => {
    const saved = window.localStorage.getItem(COLLAPSE_STORAGE_KEY);
    if (saved === "1") setStoredCollapsed(true);
  }, []);

  const toggleCollapsed = () => {
    setStoredCollapsed((prev) => {
      const next = !prev;
      window.localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  };

  return (
    <nav className={`${styles.sidebar} ${isCollapsed ? styles.collapsed : ""}`} aria-label="Dashboard navigation">
      <div className={styles.brand}>
        {isCollapsed ? <Logo variant="mark" size={22} /> : <Logo size={22} />}
      </div>

      {/* Workspace selector -- shows the real current business (whatever
          the account is actually named, e.g. "Taboo"), not a hardcoded
          label. Reuses the existing multi-business switching already in
          DashboardContext; this is only a visual entry point into that
          existing capability, not new switching logic. */}
      {primaryBusiness && !isCollapsed && (
        <div className={styles.workspaceWrap} ref={switcherRef}>
          <button
            className={styles.workspaceButton}
            onClick={() => setIsSwitcherOpen((open) => !open)}
            aria-expanded={isSwitcherOpen}
          >
            <span className={styles.workspaceAvatar}>{primaryBusiness.name.charAt(0).toUpperCase()}</span>
            <span className={styles.workspaceName}>{primaryBusiness.name}</span>
            <span className={styles.workspaceChevron} aria-hidden="true">
              ▾
            </span>
          </button>
          {isSwitcherOpen && businesses.length > 1 && (
            <div className={styles.workspaceMenu}>
              {businesses.map((business) => (
                <button
                  key={business.id}
                  className={styles.workspaceMenuItem}
                  onClick={() => {
                    selectBusiness(business.id);
                    setIsSwitcherOpen(false);
                  }}
                >
                  {business.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className={styles.navScroll}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className={styles.navGroup}>
            {!isCollapsed && <span className={styles.navGroupLabel}>{group.label}</span>}
            <ul className={styles.navList}>
              {group.items.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      className={`${styles.navLink} ${isActive ? styles.navLinkActive : ""}`}
                      aria-current={isActive ? "page" : undefined}
                      title={isCollapsed ? item.label : undefined}
                    >
                      <NavIcon name={item.icon} />
                      {!isCollapsed && <span>{item.label}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {!forceExpanded && (
        <button
          className={styles.collapseToggle}
          onClick={toggleCollapsed}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className={styles.collapseIcon}>{isCollapsed ? "»" : "«"}</span>
          {!isCollapsed && <span>Collapse</span>}
        </button>
      )}
    </nav>
  );
}

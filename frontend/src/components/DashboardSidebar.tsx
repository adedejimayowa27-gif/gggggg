"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./DashboardSidebar.module.css";

interface NavItem {
  label: string;
  href: string;
  enabled: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", enabled: true },
  { label: "Alerts", href: "/dashboard/alerts", enabled: true },
  { label: "Transactions", href: "/dashboard/transactions", enabled: true },
  { label: "Products", href: "/dashboard/products", enabled: true },
  { label: "Analytics", href: "/dashboard/analytics", enabled: true },
  { label: "Simulator", href: "/dashboard/simulator", enabled: true },
  { label: "AI Assistant", href: "/dashboard/ai-assistant", enabled: true },
  { label: "Settings", href: "/dashboard/settings", enabled: false },
];

interface Props {
  onNavigate?: () => void;
}

export default function DashboardSidebar({ onNavigate }: Props) {
  const pathname = usePathname();

  return (
    <nav className={styles.sidebar} aria-label="Dashboard navigation">
      <div className={styles.brand}>
        <span className={styles.brandMark}>Mayorcity Bizintel</span>
      </div>

      <ul className={styles.navList}>
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                className={[
                  styles.navLink,
                  isActive ? styles.navLinkActive : "",
                  !item.enabled ? styles.navLinkDisabled : "",
                ].join(" ")}
                aria-current={isActive ? "page" : undefined}
              >
                <span>{item.label}</span>
                {!item.enabled && <span className={styles.badge}>Soon</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * Compact shortcuts to the app's existing capabilities -- every action
 * here links to a page/flow that already exists; nothing new is built
 * to support this panel.
 *
 * Note: the brief this was designed against asked for "Add product" as
 * one of the four actions. There's no such feature in this app --
 * products aren't standalone entities, they're just distinct product
 * names that emerge from imported transaction data (see the Products
 * page, which is read-only analytics derived from transactions). Rather
 * than build a fake "add product" form with nothing real behind it, or
 * silently drop the brief's fourth action, this substitutes "Connect a
 * data source" (Google Sheets/OneDrive, both real existing
 * integrations) -- genuinely useful, and the honest equivalent of "get
 * more product data into the system" for an app where products come
 * from transactions.
 */
import Link from "next/link";
import NavIcon from "@/components/NavIcon";
import styles from "./QuickActionsPanel.module.css";

function LinkIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="9" width="8" height="4" rx="2" />
      <rect x="10" y="7" width="8" height="4" rx="2" />
    </svg>
  );
}

function ImportIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10 2V13" />
      <path d="M6 9L10 13L14 9" />
      <path d="M4 15V17A1 1 0 005 18H15A1 1 0 0016 17V15" />
    </svg>
  );
}

interface Action {
  label: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  accent: "gold" | "leaf" | "purple" | "blue";
}

const ACTIONS: Action[] = [
  {
    label: "Import transactions",
    description: "Upload a spreadsheet of sales",
    href: "/dashboard/transactions",
    icon: <ImportIcon />,
    accent: "gold",
  },
  {
    label: "Connect a data source",
    description: "Sync from Google Sheets or Excel",
    href: "/dashboard/settings",
    icon: <LinkIcon />,
    accent: "blue",
  },
  {
    label: "View all transactions",
    description: "Browse your full sales history",
    href: "/dashboard/transactions",
    icon: <NavIcon name="transactions" />,
    accent: "leaf",
  },
  {
    label: "Run AI analysis",
    description: "Ask a question about your business",
    href: "/dashboard/ai-assistant",
    icon: <NavIcon name="ai" />,
    accent: "purple",
  },
];

export default function QuickActionsPanel() {
  return (
    <div className={styles.panel}>
      <h2 className={styles.title}>Quick Actions</h2>
      <div className={styles.list}>
        {ACTIONS.map((action) => (
          <Link key={action.label} href={action.href} className={styles.action}>
            <span className={`${styles.iconWrap} ${styles[`accent_${action.accent}`]}`}>{action.icon}</span>
            <span>
              <span className={styles.actionLabel}>{action.label}</span>
              <span className={styles.actionDescription}>{action.description}</span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

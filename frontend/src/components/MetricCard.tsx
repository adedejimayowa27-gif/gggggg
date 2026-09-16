"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useClickOutside } from "@/hooks/useClickOutside";
import Sparkline from "@/components/Sparkline";
import styles from "./MetricCard.module.css";

export type MetricIcon = "revenue" | "profit" | "margin" | "transactions" | "products";
export type MetricAccent = "gold" | "leaf" | "purple" | "blue" | "neutral";

const ACCENT_VAR: Record<MetricAccent, string> = {
  gold: "var(--gold)",
  leaf: "var(--leaf)",
  purple: "var(--viz-purple)",
  blue: "var(--viz-blue)",
  neutral: "var(--sage)",
};

// Separate from ACCENT_VAR: a tinted icon-background needs both a text
// color and a translucent version of that same color for the chip
// behind it. Concatenating an alpha suffix onto a `var(--x)` string
// (e.g. `${accentColor}1F`) is not valid CSS -- a var() reference can't
// have a hex suffix appended to it like a literal hex code can -- so
// each accent's tint is its own fixed, pre-mixed color here instead.
const ACCENT_TINT_CLASS: Record<MetricAccent, string> = {
  gold: "iconGold",
  leaf: "iconLeaf",
  purple: "iconPurple",
  blue: "iconBlue",
  neutral: "iconNeutral",
};

interface Props {
  label: string;
  icon: MetricIcon;
  accent?: MetricAccent;
  /** True while data is being fetched -- renders a pulsing skeleton
   * placeholder, distinct from isEmpty (which means the fetch finished
   * and there's genuinely nothing to show). Conflating these into one
   * flag was the original version of this component's mistake: a card
   * that was still loading looked identical to one confirmed empty,
   * which reads as "this business has no data" for a fraction of a
   * second on every single page load, even for businesses with months
   * of real numbers. */
  isLoading?: boolean;
  isEmpty?: boolean;
  emptyText?: string;
  value?: string;
  /** Percentage change vs. the comparison period, e.g. 18.4 for "+18.4%".
   * Omit (or pass null) for a card that has nothing meaningful to
   * compare yet -- never fabricate a number here. */
  changePercent?: number | null;
  changeLabel?: string;
  /** Real period-over-period values for the sparkline, or omit entirely
   * -- a card with no backing timeseries data (see MetricCard usage on
   * the Overview page) simply doesn't render one, rather than drawing a
   * fake trend line. */
  sparklineValues?: number[] | null;
  /** Where "View details" in the card's menu goes. */
  detailsHref?: string;
}

function Icon({ type }: { type: MetricIcon }) {
  const common = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none" };

  switch (type) {
    case "revenue":
      return (
        <svg {...common}>
          <path
            d="M12 2v20M17 5.5c0-1.93-2.24-3.5-5-3.5s-5 1.57-5 3.5S9.24 9 12 9s5 1.57 5 3.5-2.24 3.5-5 3.5-5-1.57-5-3.5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      );
    case "profit":
      return (
        <svg {...common}>
          <path
            d="M3 17l6-6 4 4 8-8M21 7v6M21 7h-6"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "margin":
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.6" />
          <circle cx="17" cy="17" r="3" stroke="currentColor" strokeWidth="1.6" />
          <path d="M18 6L6 18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "transactions":
      return (
        <svg {...common}>
          <path
            d="M4 6h16M4 6v13a1 1 0 001 1h14a1 1 0 001-1V6M4 6l1.5-3h13L20 6"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M9 11h6M9 15h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "products":
      return (
        <svg {...common}>
          <path
            d="M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
  }
}

export default function MetricCard({
  label,
  icon,
  accent = "neutral",
  isLoading = false,
  isEmpty = true,
  emptyText,
  value,
  changePercent,
  changeLabel,
  sparklineValues,
  detailsHref,
}: Props) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useClickOutside(menuRef, isMenuOpen, () => setIsMenuOpen(false));

  const accentColor = ACCENT_VAR[accent];
  const isPositive = typeof changePercent === "number" && changePercent >= 0;

  return (
    <div className={styles.card}>
      <div className={styles.cardTop}>
        <div className={`${styles.iconWrap} ${styles[ACCENT_TINT_CLASS[accent]]}`}>
          <Icon type={icon} />
        </div>

        {detailsHref && (
          <div className={styles.menuWrap} ref={menuRef}>
            <button
              className={styles.menuButton}
              onClick={() => setIsMenuOpen((open) => !open)}
              aria-label={`${label} options`}
              aria-expanded={isMenuOpen}
            >
              <span className={styles.dots}>&#8226;&#8226;&#8226;</span>
            </button>
            {isMenuOpen && (
              <div className={styles.menu}>
                <Link href={detailsHref} className={styles.menuItem} onClick={() => setIsMenuOpen(false)}>
                  View details
                </Link>
              </div>
            )}
          </div>
        )}
      </div>

      <div className={styles.label}>{label}</div>

      {isLoading ? (
        <div className={styles.skeleton}>
          <span className={styles.skeletonValue} />
          <span className={styles.skeletonChange} />
        </div>
      ) : isEmpty ? (
        <>
          <div className={styles.emptyValue}>—</div>
          <div className={styles.emptyText}>{emptyText || "No data yet"}</div>
        </>
      ) : (
        <div className={styles.valueRow}>
          <div>
            <div className={styles.value}>{value}</div>
            {typeof changePercent === "number" && (
              <div className={`${styles.change} ${isPositive ? styles.changeUp : styles.changeDown}`}>
                {isPositive ? "▲" : "▼"} {Math.abs(changePercent).toFixed(1)}%
                {changeLabel && <span className={styles.changeLabel}> {changeLabel}</span>}
              </div>
            )}
          </div>
          {sparklineValues && sparklineValues.length > 1 && (
            <Sparkline values={sparklineValues} color={accentColor} />
          )}
        </div>
      )}
    </div>
  );
}

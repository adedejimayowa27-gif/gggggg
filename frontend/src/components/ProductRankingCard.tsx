"use client";

/**
 * Product ranking card.
 *
 * Renders one of the four ranked lists from GET .../analytics/products
 * (top-selling, highest-profit, lowest-profit, slow-moving). All four
 * share the same shape -- a ranked list of ProductAnalyticsItem -- so
 * one component handles all of them, parameterized by which field to
 * feature as the headline metric.
 *
 * Visual language matches MetricCard / TopProductsPanel from the
 * Overview redesign: a tinted icon chip identifies each card at a
 * glance, rows get a colored rank badge (the same "initial avatar"
 * treatment as TopProductsPanel, just numbered), and a thin magnitude
 * bar under each row shows how it stacks up against the biggest number
 * in its own list -- so the ranking is felt at a glance, not just read
 * off a column of numbers.
 */
import type { ProductAnalyticsItem } from "@/types";
import styles from "./ProductRankingCard.module.css";

type PrimaryMetric = "units_sold" | "gross_profit";
export type RankingAccent = "gold" | "leaf" | "clay" | "blue";
export type RankingIcon = "units" | "trendUp" | "trendDown" | "clock";

interface Props {
  title: string;
  description: string;
  items: ProductAnalyticsItem[];
  primaryMetric: PrimaryMetric;
  icon: RankingIcon;
  accent: RankingAccent;
  isLoading?: boolean;
  error?: string | null;
}

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

function formatCurrency(value: string): string {
  return currencyFormatter.format(Number(value));
}

function formatNumber(value: string): string {
  return numberFormatter.format(Number(value));
}

function primaryValue(item: ProductAnalyticsItem, metric: PrimaryMetric): string {
  return metric === "units_sold" ? formatNumber(item.units_sold) : formatCurrency(item.gross_profit);
}

function primaryLabel(metric: PrimaryMetric): string {
  return metric === "units_sold" ? "units" : "profit";
}

/** Absolute size used to scale each row's magnitude bar -- abs() so a
 * list of losses (lowest-profit, all negative) still produces a
 * meaningful, non-zero-width bar relative to its own worst offender,
 * rather than every bar collapsing because the "biggest" value is
 * technically the least negative one. */
function magnitude(item: ProductAnalyticsItem, metric: PrimaryMetric): number {
  const raw = metric === "units_sold" ? Number(item.units_sold) : Number(item.gross_profit);
  return Math.abs(raw);
}

function Icon({ type }: { type: RankingIcon }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none" };
  switch (type) {
    case "units":
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
    case "trendUp":
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
    case "trendDown":
      return (
        <svg {...common}>
          <path
            d="M3 7l6 6 4-4 8 8M21 17v-6M21 17h-6"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "clock":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="M12 7v5l3.5 2"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
  }
}

const ICON_TINT_CLASS: Record<RankingAccent, string> = {
  gold: "iconGold",
  leaf: "iconLeaf",
  clay: "iconClay",
  blue: "iconBlue",
};

const BADGE_CLASS: Record<RankingAccent, string> = {
  gold: "badgeGold",
  leaf: "badgeLeaf",
  clay: "badgeClay",
  blue: "badgeBlue",
};

const FILL_CLASS: Record<RankingAccent, string> = {
  gold: "fillGold",
  leaf: "fillLeaf",
  clay: "fillClay",
  blue: "fillBlue",
};

export default function ProductRankingCard({
  title,
  description,
  items,
  primaryMetric,
  icon,
  accent,
  isLoading = false,
  error = null,
}: Props) {
  const maxMagnitude =
    items.length > 0 ? Math.max(...items.map((item) => magnitude(item, primaryMetric)), 1) : 1;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={`${styles.iconWrap} ${styles[ICON_TINT_CLASS[accent]]}`}>
          <Icon type={icon} />
        </div>
        <div className={styles.headerText}>
          <h2 className={styles.title}>{title}</h2>
          <p className={styles.description}>{description}</p>
        </div>
      </div>

      {isLoading ? (
        <div className={styles.skeletonList}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className={styles.skeletonRow}>
              <span className={styles.skeletonBadge} />
              <span className={styles.skeletonLine} />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className={styles.stateBox}>
          <p className={styles.stateTitle}>Couldn&rsquo;t load this list</p>
          <p className={styles.stateBody}>{error}</p>
        </div>
      ) : items.length === 0 ? (
        <div className={styles.stateBox}>
          <p className={styles.stateTitle}>Nothing here yet</p>
          <p className={styles.stateBody}>No products in this range yet.</p>
        </div>
      ) : (
        <ol className={styles.list}>
          {items.map((item, index) => {
            const profitIsNegative = Number(item.gross_profit) < 0;
            const barWidth = Math.max((magnitude(item, primaryMetric) / maxMagnitude) * 100, 3);
            return (
              <li key={item.product} className={styles.row}>
                <div className={styles.rowTop}>
                  <span className={`${styles.badge} ${styles[BADGE_CLASS[accent]]}`}>
                    {index + 1}
                  </span>
                  <div className={styles.rowMain}>
                    <span className={styles.productName}>{item.product}</span>
                    <span className={styles.rowSub}>
                      {formatNumber(item.units_sold)} sold · {formatCurrency(item.revenue)} revenue
                    </span>
                  </div>
                  <div className={styles.rowMetric}>
                    <span
                      className={`${styles.metricValue} ${
                        primaryMetric === "gross_profit" && profitIsNegative ? styles.metricNegative : ""
                      }`}
                    >
                      {primaryValue(item, primaryMetric)}
                    </span>
                    <span className={styles.metricLabel}>{primaryLabel(primaryMetric)}</span>
                  </div>
                </div>
                <div className={styles.barTrack}>
                  <div
                    className={`${styles.barFill} ${styles[FILL_CLASS[accent]]}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

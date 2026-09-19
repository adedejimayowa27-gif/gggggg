"use client";

/**
 * Period-over-period variance table.
 *
 * The classic Excel "Actual / Prior / Δ%" grid -- every core metric in
 * one glanceable table instead of six separate cards. Deliberately not
 * self-fetching: the Analytics page already fetches summary and
 * previousSummary for Batch 1's KPI strip, and this table describes
 * that exact same pair of periods, so it takes them as props rather
 * than issuing a second, potentially-inconsistent fetch.
 */
import { percentChange } from "@/lib/analytics";
import type { AnalyticsSummary } from "@/types";
import styles from "./VarianceSummaryTable.module.css";

interface Props {
  summary: AnalyticsSummary | null;
  previousSummary: AnalyticsSummary | null;
  isLoading: boolean;
  error: string | null;
}

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 2,
});

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

interface Row {
  label: string;
  current: number;
  previous: number;
  format: "currency" | "number" | "percentPoints";
}

function formatValue(value: number, format: Row["format"]): string {
  if (format === "currency") return currencyFormatter.format(value);
  if (format === "percentPoints") return `${numberFormatter.format(value)}%`;
  return numberFormatter.format(value);
}

function buildRows(summary: AnalyticsSummary, previous: AnalyticsSummary): Row[] {
  return [
    { label: "Revenue", current: Number(summary.revenue), previous: Number(previous.revenue), format: "currency" },
    {
      label: "Gross profit",
      current: Number(summary.gross_profit),
      previous: Number(previous.gross_profit),
      format: "currency",
    },
    {
      label: "Profit margin",
      current: Number(summary.profit_margin),
      previous: Number(previous.profit_margin),
      format: "percentPoints",
    },
    {
      label: "Avg. transaction value",
      current: Number(summary.average_transaction_value),
      previous: Number(previous.average_transaction_value),
      format: "currency",
    },
    {
      label: "Transactions",
      current: summary.transaction_count,
      previous: previous.transaction_count,
      format: "number",
    },
    {
      label: "Units sold",
      current: Number(summary.units_sold),
      previous: Number(previous.units_sold),
      format: "number",
    },
  ];
}

export default function VarianceSummaryTable({ summary, previousSummary, isLoading, error }: Props) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.iconWrap}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 4v16h16M8 15l3-4 3 2 4-6"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div>
          <h2 className={styles.title}>Period comparison</h2>
          <p className={styles.description}>Every core metric, actual vs. the previous period</p>
        </div>
      </div>

      {isLoading ? (
        <div className={styles.placeholder}>Loading…</div>
      ) : error ? (
        <div className={styles.placeholder}>{error}</div>
      ) : !summary || !previousSummary ? (
        <div className={styles.placeholder}>Not enough history yet to compare periods</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Metric</th>
                <th>This period</th>
                <th>Previous period</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {buildRows(summary, previousSummary).map((row) => {
                const isMargin = row.format === "percentPoints";
                const delta = isMargin ? row.current - row.previous : null;
                const pctChange = isMargin ? null : percentChange(row.current, row.previous);
                const changeValue = isMargin ? delta : pctChange;
                const isPositive = (changeValue ?? 0) > 0;
                const isNegative = (changeValue ?? 0) < 0;
                return (
                  <tr key={row.label}>
                    <td className={styles.metricCell}>{row.label}</td>
                    <td>{formatValue(row.current, row.format)}</td>
                    <td className={styles.previousCell}>{formatValue(row.previous, row.format)}</td>
                    <td>
                      {changeValue === null ? (
                        <span className={styles.changeNeutral}>—</span>
                      ) : (
                        <span
                          className={
                            isPositive ? styles.changePositive : isNegative ? styles.changeNegative : styles.changeNeutral
                          }
                        >
                          {isPositive ? "▲" : isNegative ? "▼" : "–"}{" "}
                          {numberFormatter.format(Math.abs(changeValue))}
                          {isMargin ? "pp" : "%"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

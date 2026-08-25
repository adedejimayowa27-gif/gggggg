import styles from "./MetricCard.module.css";

export type MetricIcon = "revenue" | "profit" | "margin" | "transactions" | "products";

interface Props {
  label: string;
  icon: MetricIcon;
  isEmpty?: boolean;
  emptyText?: string;
  value?: string;
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

export default function MetricCard({ label, icon, isEmpty = true, emptyText, value }: Props) {
  return (
    <div className={styles.card}>
      <div className={styles.iconWrap}>
        <Icon type={icon} />
      </div>
      <div className={styles.label}>{label}</div>
      {isEmpty ? (
        <>
          <div className={styles.emptyValue}>—</div>
          <div className={styles.emptyText}>{emptyText || "No data yet"}</div>
        </>
      ) : (
        <div className={styles.value}>{value}</div>
      )}
    </div>
  );
}

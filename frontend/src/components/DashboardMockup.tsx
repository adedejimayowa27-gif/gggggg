/**
 * A realistic miniature Bizintel dashboard -- replaces the earlier
 * abstract line-illustration with something that actually looks like
 * the product: real metric cards, a real sales-trend-plus-forecast
 * chart, and a floating AI alert card. Built with real HTML/CSS for
 * the chrome (so text stays crisp/selectable at any size) and one
 * inline SVG for the chart line itself, since a chart is the one part
 * that's naturally a path.
 *
 * Static (no live data, no animation loop) -- this is marketing, not a
 * real dashboard instance, and it should never claim to be showing an
 * actual business's real numbers.
 */
import Logo from "@/components/Logo";
import styles from "./DashboardMockup.module.css";

export default function DashboardMockup() {
  return (
    <div className={`${styles.frame} bgGrid`} aria-hidden="true">
      <div className={styles.header}>
        <Logo variant="mark" size={16} />
        <span className={styles.headerLabel}>This month</span>
        <span className={styles.livePill}>
          <span className={styles.liveDot} />
          Live
        </span>
      </div>

      <div className={styles.metrics}>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>Revenue</span>
          <span className={styles.metricValue}>₦4,820,000</span>
          <span className={styles.metricChangeUp}>▲ 18% vs last month</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricLabel}>Profit margin</span>
          <span className={styles.metricValue}>34.2%</span>
          <span className={styles.metricChangeUp}>▲ 3.1pts vs last month</span>
        </div>
      </div>

      <div className={styles.chartCard}>
        <div className={styles.chartHeaderRow}>
          <span className={styles.chartTitle}>Sales trend</span>
          <span className={styles.forecastTag}>Forecast</span>
        </div>
        <svg viewBox="0 0 440 140" className={styles.chartSvg} preserveAspectRatio="none">
          <defs>
            <linearGradient id="mockupFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--viz-blue)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--viz-blue)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path
            d="M0 120 L55 105 L110 110 L165 85 L220 90 L275 55 L330 40 L330 140 L0 140 Z"
            fill="url(#mockupFill)"
          />
          <path
            d="M0 120 L55 105 L110 110 L165 85 L220 90 L275 55 L330 40"
            fill="none"
            stroke="var(--viz-blue)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M330 40 L385 28 L440 15"
            fill="none"
            stroke="var(--viz-purple)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray="2 6"
          />
          <circle cx="330" cy="40" r="4" fill="var(--viz-blue)" />
          <circle cx="440" cy="15" r="4" fill="var(--viz-purple)" />
        </svg>
      </div>

      <div className={`${styles.alertCard} glass`}>
        <span className={styles.alertIcon}>!</span>
        <div>
          <p className={styles.alertLabel}>AI alert</p>
          <p className={styles.alertText}>Widget sales dropped 12% this week -- check pricing.</p>
        </div>
      </div>
    </div>
  );
}

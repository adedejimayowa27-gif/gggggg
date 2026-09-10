/**
 * Brand mark + wordmark for Mayorcity Bizintel.
 *
 * The mark: three ascending bars (a chart -- the raw data) with the
 * tallest bar's corner opening into an arrowhead (the answer the data
 * points to). One shape doing two jobs -- "this is a data product" and
 * "things are moving in a clear direction" -- rather than a literal
 * chart icon paired with a separate arrow icon.
 *
 * `variant="mark"` renders just the icon (used in tight spaces like a
 * collapsed sidebar); `variant="full"` (default) renders the mark plus
 * the wordmark, split across two weights of the same display face
 * rather than two colors, so it still reads correctly in print/mono
 * contexts and doesn't rely on color for meaning.
 */
import styles from "./Logo.module.css";

interface Props {
  variant?: "full" | "mark";
  size?: number;
  className?: string;
}

export default function Logo({ variant = "full", size = 28, className }: Props) {
  const mark = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Three ascending bars -- the raw data -- with a small chevron
          capping the tallest one, reading as an arrowhead: the answer
          the data points to, not just a chart of it. */}
      <rect x="4" y="18" width="5" height="10" rx="1.25" fill="currentColor" />
      <rect x="13.5" y="11" width="5" height="17" rx="1.25" fill="currentColor" />
      <rect x="23" y="6" width="5" height="22" rx="1.25" fill="currentColor" />
      <path d="M25.5 0L29.5 7H21.5L25.5 0Z" fill="currentColor" />
    </svg>
  );

  if (variant === "mark") {
    return <span className={`${styles.mark} ${className ?? ""}`}>{mark}</span>;
  }

  return (
    <span className={`${styles.lockup} ${className ?? ""}`}>
      <span className={styles.mark}>{mark}</span>
      <span className={styles.wordmark}>
        <span className={styles.wordPrimary}>Mayorcity</span>
        <span className={styles.wordSecondary}>Bizintel</span>
      </span>
    </span>
  );
}

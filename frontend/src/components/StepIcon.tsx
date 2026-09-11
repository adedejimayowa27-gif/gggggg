/**
 * The three small line icons for the landing page's "How it works"
 * section -- kept as one component (rather than three separate files)
 * since they're only ever used together, in this one place, at this
 * one size.
 */
import styles from "./StepIcon.module.css";

type Variant = "import" | "analyze" | "decide";

const COLOR_VAR: Record<Variant, string> = {
  import: "var(--gold)",
  analyze: "var(--viz-blue)",
  decide: "var(--viz-purple)",
};

const TINT_CLASS: Record<Variant, string> = {
  import: styles.tintGold,
  analyze: styles.tintBlue,
  decide: styles.tintPurple,
};

function IconPath({ variant }: { variant: Variant }) {
  if (variant === "import") {
    return (
      <>
        <path d="M12 3V15" />
        <path d="M7 10L12 15L17 10" />
        <path d="M4 15V20H20V15" />
      </>
    );
  }
  if (variant === "analyze") {
    return (
      <>
        <rect x="3" y="14" width="4" height="6" rx="1" fill="currentColor" stroke="none" />
        <rect x="10" y="8" width="4" height="12" rx="1" fill="currentColor" stroke="none" />
        <rect x="17" y="3" width="4" height="17" rx="1" fill="currentColor" stroke="none" />
      </>
    );
  }
  return (
    <>
      <path d="M3 7H21" />
      <circle cx="15" cy="7" r="2.4" fill="currentColor" stroke="none" />
      <path d="M3 17H21" />
      <circle cx="9" cy="17" r="2.4" fill="currentColor" stroke="none" />
    </>
  );
}

export default function StepIcon({ variant }: { variant: Variant }) {
  return (
    <span className={`${styles.badge} ${TINT_CLASS[variant]}`} style={{ color: COLOR_VAR[variant] }}>
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <IconPath variant={variant} />
      </svg>
    </span>
  );
}

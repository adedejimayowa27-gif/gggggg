import Link from "next/link";
import Logo from "@/components/Logo";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <Logo />
        <div className={styles.navActions}>
          <Link href="/login" className={styles.navLogin}>
            Log in
          </Link>
          <Link href="/signup" className={styles.navCta}>
            Get started
          </Link>
        </div>
      </nav>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <h1 className={styles.heroHeadline}>Your sales data, finally making sense.</h1>
          <p className={styles.heroSub}>
            Upload your transactions from Excel, CSV, Google Sheets, or OneDrive, and Mayorcity
            Bizintel turns them into clear answers -- what&apos;s selling, what&apos;s slipping,
            and what happens if you change your prices tomorrow.
          </p>
          <div className={styles.heroActions}>
            <Link href="/signup" className={styles.primaryButton}>
              Get started
            </Link>
            <a href="#how-it-works" className={styles.secondaryLink}>
              See how it works
            </a>
          </div>
          <p className={styles.trustLine}>
            Works with the Excel sheets and Google Sheets you already use to track sales.
          </p>
        </div>

        <div className={styles.heroVisual} aria-hidden="true">
          <svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#E1A335" stopOpacity="0.18" />
                <stop offset="100%" stopColor="#E1A335" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path
              d="M20 320 L100 280 L180 230 L260 150 L340 60 L340 380 L20 380 Z"
              fill="url(#heroFill)"
            />
            <path
              d="M20 320 L100 280 L180 230 L260 150 L340 60"
              fill="none"
              stroke="#E1A335"
              strokeWidth="5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="20" cy="320" r="6" fill="#E1A335" />
            <circle cx="100" cy="280" r="7" fill="#E1A335" />
            <circle cx="180" cy="230" r="8" fill="#E1A335" />
            <circle cx="260" cy="150" r="9" fill="#E1A335" />
            <circle cx="340" cy="60" r="11" fill="#E1A335" />
            <circle cx="300" cy="220" r="7" fill="#5C9A6F" />
            <circle cx="120" cy="110" r="6" fill="#C8593F" />
          </svg>
        </div>
      </section>

      <section className={styles.howItWorks} id="how-it-works">
        <h2 className={styles.sectionHeading}>How it works</h2>
        <div className={styles.stepGrid}>
          <div className={styles.step}>
            <h3 className={styles.stepTitle}>Bring in your data</h3>
            <p className={styles.stepBody}>
              Upload a spreadsheet, or connect Google Sheets or OneDrive once. After that,
              Mayorcity keeps checking for new sales on its own, and never double-counts a
              transaction you&apos;ve already imported.
            </p>
          </div>
          <div className={styles.step}>
            <h3 className={styles.stepTitle}>See what&apos;s actually happening</h3>
            <p className={styles.stepBody}>
              Revenue, cost, and profit broken down by product, category, and time period -- the
              numbers your gut feeling can&apos;t give you.
            </p>
          </div>
          <div className={styles.step}>
            <h3 className={styles.stepTitle}>Decide with confidence</h3>
            <p className={styles.stepBody}>
              Try a price change or a slower month in the simulator before it happens for real,
              and get alerted the moment something in your numbers looks off.
            </p>
          </div>
        </div>
      </section>

      <section className={styles.closing}>
        <p className={styles.closingHeadline}>Start seeing your numbers clearly.</p>
        <Link href="/signup" className={styles.primaryButton}>
          Get started
        </Link>
      </section>

      <footer className={styles.footer}>
        <Logo variant="mark" size={20} />
        <p className={styles.footerNote}>© {new Date().getFullYear()} Mayorcity Bizintel</p>
      </footer>
    </main>
  );
}

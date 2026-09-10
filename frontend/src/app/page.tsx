import Link from "next/link";
import Logo from "@/components/Logo";
import LandingNav from "@/components/LandingNav";
import DashboardMockup from "@/components/DashboardMockup";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.page}>
      <LandingNav />

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

        <div className={styles.heroVisual}>
          <DashboardMockup />
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

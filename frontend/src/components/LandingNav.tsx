"use client";

/**
 * Split out from page.tsx (which is otherwise a Server Component) since
 * the scroll-aware glass effect needs a scroll listener, which only
 * works in a Client Component. Everything else on the landing page
 * stays server-rendered.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import Logo from "@/components/Logo";
import InstallAppButton from "@/components/InstallAppButton";
import styles from "./LandingNav.module.css";

export default function LandingNav() {
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 8);
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav className={`${styles.nav} ${isScrolled ? styles.navScrolled : ""}`}>
      <Link href="/" className={styles.logoLink}>
        <Logo responsive />
      </Link>
      <div className={styles.navActions}>
        <InstallAppButton className={styles.installButton} />
        <Link href="/login" className={styles.navLogin}>
          Log in
        </Link>
        <Link href="/signup" className={styles.navCta}>
          Get started
        </Link>
      </div>
    </nav>
  );
}

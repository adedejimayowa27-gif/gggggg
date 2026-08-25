"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { DashboardProvider } from "@/context/DashboardContext";
import DashboardSidebar from "@/components/DashboardSidebar";
import DashboardTopbar from "@/components/DashboardTopbar";
import styles from "./dashboard.module.css";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  // Route protection: this is the single guard for the entire /dashboard/*
  // tree. Individual pages don't need to repeat this check.
  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    }
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return (
      <main className={styles.centered}>
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      </main>
    );
  }

  return (
    <DashboardProvider>
      <div className={styles.shell}>
        <div className={styles.sidebarDesktop}>
          <DashboardSidebar />
        </div>

        {isMobileNavOpen && (
          <>
            <div className={styles.overlay} onClick={() => setIsMobileNavOpen(false)} />
            <div className={`${styles.drawer} ${styles.drawerOpen}`}>
              <DashboardSidebar onNavigate={() => setIsMobileNavOpen(false)} />
            </div>
          </>
        )}

        <div className={styles.main}>
          <DashboardTopbar onMenuToggle={() => setIsMobileNavOpen((open) => !open)} />
          <div className={styles.content}>{children}</div>
        </div>
      </div>
    </DashboardProvider>
  );
}

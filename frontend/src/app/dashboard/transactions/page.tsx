"use client";

/**
 * useSearchParams() requires a Suspense boundary around whatever calls
 * it, or Next's static-export step fails at build time -- same issue as
 * reset-password/page.tsx, same fix: the actual content lives in
 * TransactionsPageContent, and the default export just wraps it in
 * <Suspense>.
 */
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import TransactionImportWizard from "@/components/TransactionImportWizard";
import TransactionsTable from "@/components/TransactionsTable";
import ImportHistoryList from "@/components/ImportHistoryList";
import styles from "./transactions.module.css";

function TransactionsPageContent() {
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const [refreshSignal, setRefreshSignal] = useState(0);
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") ?? undefined;

  if (isLoadingBusinesses) {
    return <p className={styles.muted}>Loading…</p>;
  }

  if (!primaryBusiness) {
    return (
      <div>
        <h1 className={styles.title}>Transactions</h1>
        <p className={styles.muted}>
          Create a business on the Overview page before uploading transactions.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div>
        <h1 className={styles.title}>Transactions</h1>
        <TransactionImportWizard
          businessId={primaryBusiness.id}
          onImportComplete={() => setRefreshSignal((s) => s + 1)}
        />
      </div>

      <div>
        <h2 className={styles.sectionTitle}>Import History</h2>
        <ImportHistoryList businessId={primaryBusiness.id} refreshSignal={refreshSignal} />
      </div>

      <div>
        <h2 className={styles.sectionTitle}>All Transactions</h2>
        <TransactionsTable businessId={primaryBusiness.id} refreshSignal={refreshSignal} initialQuery={initialQuery} />
      </div>
    </div>
  );
}

export default function TransactionsPage() {
  return (
    <Suspense fallback={<p className={styles.muted}>Loading…</p>}>
      <TransactionsPageContent />
    </Suspense>
  );
}

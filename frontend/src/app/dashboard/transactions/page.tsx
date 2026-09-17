"use client";

import { useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import TransactionImportWizard from "@/components/TransactionImportWizard";
import TransactionsTable from "@/components/TransactionsTable";
import ImportHistoryList from "@/components/ImportHistoryList";
import styles from "./transactions.module.css";

export default function TransactionsPage() {
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const [refreshSignal, setRefreshSignal] = useState(0);

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
        <TransactionsTable businessId={primaryBusiness.id} refreshSignal={refreshSignal} />
      </div>
    </div>
  );
}

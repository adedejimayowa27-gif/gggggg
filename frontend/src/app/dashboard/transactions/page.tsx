"use client";

import { useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import TransactionImportWizard from "@/components/TransactionImportWizard";
import TransactionsTable from "@/components/TransactionsTable";
import ImportHistoryList from "@/components/ImportHistoryList";

export default function TransactionsPage() {
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();
  const [refreshSignal, setRefreshSignal] = useState(0);

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness) {
    return (
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          Transactions
        </h1>
        <p style={{ color: "var(--muted)" }}>
          Create a business on the Overview page before uploading transactions.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "1.5rem" }}>
          Transactions
        </h1>
        <TransactionImportWizard
          businessId={primaryBusiness.id}
          onImportComplete={() => setRefreshSignal((s) => s + 1)}
        />
      </div>

      <div>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Import History
        </h2>
        <ImportHistoryList businessId={primaryBusiness.id} refreshSignal={refreshSignal} />
      </div>

      <div>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          All Transactions
        </h2>
        <TransactionsTable businessId={primaryBusiness.id} refreshSignal={refreshSignal} />
      </div>
    </div>
  );
}

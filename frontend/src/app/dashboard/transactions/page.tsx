"use client";

import { useDashboard } from "@/context/DashboardContext";
import TransactionImportWizard from "@/components/TransactionImportWizard";

export default function TransactionsPage() {
  const { primaryBusiness, isLoadingBusinesses } = useDashboard();

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
    <div>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "1.5rem" }}>
        Transactions
      </h1>
      <TransactionImportWizard businessId={primaryBusiness.id} />
    </div>
  );
}

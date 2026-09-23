"use client";

/**
 * Business settings: Google Sheets / Excel-OneDrive integrations and
 * branch management. Rebuilt after this file was found to be a
 * byte-for-byte copy of app/dashboard/simulator/page.tsx (including its
 * broken import of a CSS file that doesn't exist in this folder, which
 * is what broke the production build) -- see GoogleIntegrationCard.tsx,
 * MicrosoftIntegrationCard.tsx, and BranchManager.tsx for the actual
 * feature logic; this file just wires them to the selected business and
 * handles the OAuth-callback redirect landing back here.
 *
 * Same useSearchParams()-needs-a-Suspense-boundary requirement as
 * /verify-email/page.tsx -- split into SettingsContent for the same
 * reason.
 */
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDashboard } from "@/context/DashboardContext";
import ComingSoon from "@/components/ComingSoon";
import GoogleIntegrationCard from "@/components/GoogleIntegrationCard";
import MicrosoftIntegrationCard from "@/components/MicrosoftIntegrationCard";
import BranchManager from "@/components/BranchManager";
import styles from "./settings.module.css";

function OAuthResultNotice() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const google = searchParams.get("google");
  const microsoft = searchParams.get("microsoft");
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Clears ?google=... / ?microsoft=... from the URL once read, so a
    // page refresh doesn't keep re-showing "Connected!" -- the backend
    // callback routes (google_integration.py / microsoft_integration.py)
    // always land here with one of these params attached.
    if (google || microsoft) {
      router.replace("/dashboard/settings");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (dismissed || (!google && !microsoft)) return null;

  const isError = google === "error" || microsoft === "error";
  const service = google ? "Google Sheets" : "Excel/OneDrive";

  return (
    <div className={isError ? styles.error : styles.notice}>
      {isError
        ? `Something went wrong connecting ${service}. Please try again.`
        : `${service} connected.`}{" "}
      <button className={styles.linkButton} onClick={() => setDismissed(true)}>
        Dismiss
      </button>
    </div>
  );
}

function SettingsContent() {
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();

  if (isLoadingBusinesses) {
    return <p className={styles.muted}>Loading…</p>;
  }

  if (!primaryBusiness) {
    return <ComingSoon title="Settings" description="Create a business to configure integrations and branches." />;
  }

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Settings</h1>
          <p className={styles.subtitle}>Integrations and branches for {primaryBusiness.name}</p>
        </div>
      </div>

      <OAuthResultNotice />

      <GoogleIntegrationCard businessId={primaryBusiness.id} role={currentUserRole} />
      <MicrosoftIntegrationCard businessId={primaryBusiness.id} role={currentUserRole} />
      <BranchManager businessId={primaryBusiness.id} role={currentUserRole} />
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<p className={styles.muted}>Loading…</p>}>
      <SettingsContent />
    </Suspense>
  );
}

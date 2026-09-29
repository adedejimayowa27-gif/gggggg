"use client";

/**
 * Getting-started checklist for the Overview page (Step 13, Batch 4).
 *
 * Each step ticks itself off from the business's OWN data (sample data
 * never counts), so there's nothing to click "done" on. The card goes
 * away once every step is complete, or when dismissed (remembered per
 * business in this browser).
 *
 * Separately, whenever sample data is loaded a slim banner says so --
 * even after the checklist is dismissed -- so nobody mistakes demo
 * numbers for their real business, with the control to remove it.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import SampleDataControls from "@/components/SampleDataControls";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { getOnboardingStatus } from "@/lib/onboarding";
import { hasRole } from "@/lib/permissions";
import type { OnboardingStatus } from "@/types";
import styles from "./OnboardingChecklist.module.css";

interface Step {
  key: keyof Omit<OnboardingStatus, "has_sample_data">;
  title: string;
  hint: string;
  href: string;
  cta: string;
}

const STEPS: Step[] = [
  {
    key: "add_sales",
    title: "Add your first sales",
    hint: "Type one in, upload a file, or connect a Google Sheet or Excel file.",
    href: "/dashboard/transactions",
    cta: "Add sales",
  },
  {
    key: "record_expense",
    title: "Record your running costs",
    hint: "Rent, salaries, transport -- so your profit is the real one.",
    href: "/dashboard/expenses",
    cta: "Add expenses",
  },
  {
    key: "track_stock",
    title: "Track your stock",
    hint: "Set a reorder level and get warned before you run out.",
    href: "/dashboard/stock",
    cta: "Track stock",
  },
  {
    key: "invite_team",
    title: "Invite a teammate",
    hint: "Optional -- give someone view or edit access.",
    href: "/dashboard/team",
    cta: "Invite",
  },
];

const dismissKey = (businessId: string) => `bizintel:onboarding-dismissed:${businessId}`;

function readDismissed(businessId: string): boolean {
  try {
    return window.localStorage.getItem(dismissKey(businessId)) === "1";
  } catch {
    return false; // storage unavailable (private mode etc.) -- just show it
  }
}

interface Props {
  businessId: string;
}

export default function OnboardingChecklist({ businessId }: Props) {
  const { token } = useAuth();
  const { currentUserRole } = useDashboard();
  const canManage = hasRole(currentUserRole, "admin");

  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [dismissed, setDismissed] = useState(true); // hidden until we've actually checked

  useEffect(() => {
    if (!token) return;
    setDismissed(readDismissed(businessId));
    let cancelled = false;
    getOnboardingStatus(businessId, token)
      .then((result) => {
        if (!cancelled) setStatus(result);
      })
      .catch(() => {
        if (!cancelled) setStatus(null); // a checklist that can't load just doesn't show
      });
    return () => {
      cancelled = true;
    };
  }, [businessId, token]);

  if (!status) return null;

  const doneCount = STEPS.filter((s) => status[s.key]).length;
  const allDone = doneCount === STEPS.length;
  const showChecklist = !dismissed && !allDone;
  const offerSample = canManage && !status.has_sample_data && !status.add_sales;

  const handleDismiss = () => {
    try {
      window.localStorage.setItem(dismissKey(businessId), "1");
    } catch {
      // ignore -- it still hides for this visit
    }
    setDismissed(true);
  };

  return (
    <>
      {status.has_sample_data && (
        <div className={styles.sampleBanner} role="status">
          <span>
            <strong>You&apos;re looking at sample data.</strong> These numbers aren&apos;t your business — remove them
            whenever you&apos;re ready to add your own.
          </span>
          <SampleDataControls businessId={businessId} hasSampleData canManage={canManage} />
        </div>
      )}

      {showChecklist && (
        <section className={styles.card} aria-label="Getting started">
          <div className={styles.header}>
            <div>
              <h2 className={styles.title}>Getting started</h2>
              <p className={styles.progressText}>
                {doneCount} of {STEPS.length} done
              </p>
            </div>
            <button type="button" className={styles.dismiss} onClick={handleDismiss} aria-label="Dismiss getting started">
              ×
            </button>
          </div>

          <div className={styles.bar} aria-hidden="true">
            <div className={styles.barFill} style={{ width: `${(doneCount / STEPS.length) * 100}%` }} />
          </div>

          <ul className={styles.steps}>
            {STEPS.map((step) => {
              const done = status[step.key];
              return (
                <li key={step.key} className={`${styles.step} ${done ? styles.stepDone : ""}`}>
                  <span className={`${styles.check} ${done ? styles.checkDone : ""}`} aria-hidden="true">
                    {done ? "✓" : ""}
                  </span>
                  <div className={styles.stepText}>
                    <div className={styles.stepTitle}>{step.title}</div>
                    {!done && <div className={styles.stepHint}>{step.hint}</div>}
                  </div>
                  {!done && (
                    <Link href={step.href} className={styles.stepLink}>
                      {step.cta}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>

          {offerSample && (
            <div className={styles.sampleOffer}>
              <p className={styles.sampleText}>
                Want to see how it looks with real-looking numbers first? Load a sample shop — you can remove it in
                one click.
              </p>
              <SampleDataControls businessId={businessId} hasSampleData={false} canManage={canManage} />
            </div>
          )}
        </section>
      )}
    </>
  );
}

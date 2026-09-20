"use client";

/**
 * Billing page (frontend for Step 10, Batch 10.3's backend --
 * app/api/routes/billing.py existed with no UI calling it until now).
 *
 * GET /plans and GET .../subscription work with zero Stripe
 * configuration (every business starts on the free plan). Starting
 * checkout returns a clean 503 (code "billing_not_configured") until the
 * backend has real Stripe keys set -- shown here as an informational
 * notice, not an error, since it's an expected state before Stripe is
 * configured, not a bug.
 *
 * Reform pass: tokens instead of hardcoded hex, the same gold-contrast
 * bug fixed elsewhere fixed here too, proper currency formatting
 * (previously a raw "₦${price_ngn}" string with no thousands
 * separator), limit lines get checkmark icons instead of a bare list,
 * and the current plan's card gets a visibly highlighted border rather
 * than only a small badge easy to miss. Only one plan ("Free") is
 * actually seeded today, so the grid is built to look right at any
 * plan count rather than assuming a specific tier structure.
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { getSubscription, listPlans, startCheckout } from "@/lib/billing";
import type { Plan, Subscription } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./billing.module.css";

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  maximumFractionDigits: 0,
});

function formatPrice(priceNgn: string | number): string {
  return Number(priceNgn) === 0 ? "Free" : `${currencyFormatter.format(Number(priceNgn))}/mo`;
}

function limitText(limit: number | null, singular: string, plural: string): string {
  if (limit === null) return `Unlimited ${plural}`;
  return `${limit} ${limit === 1 ? singular : plural}`;
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function BillingPage() {
  const { token } = useAuth();
  const { primaryBusiness, isLoadingBusinesses, currentUserRole } = useDashboard();

  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notConfiguredNotice, setNotConfiguredNotice] = useState(false);
  const [upgradingPlanKey, setUpgradingPlanKey] = useState<string | null>(null);

  const canManageBilling = currentUserRole === "owner" || currentUserRole === "admin";

  useEffect(() => {
    if (!token || !primaryBusiness) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    Promise.all([listPlans(token), getSubscription(primaryBusiness.id, token)])
      .then(([plansResult, subscriptionResult]) => {
        if (cancelled) return;
        setPlans(plansResult);
        setSubscription(subscriptionResult);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load billing information.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, primaryBusiness]);

  const handleUpgrade = async (planKey: string) => {
    if (!token || !primaryBusiness) return;
    setUpgradingPlanKey(planKey);
    setNotConfiguredNotice(false);
    setError(null);
    try {
      const { checkout_url } = await startCheckout(
        primaryBusiness.id,
        {
          plan_key: planKey,
          success_url: `${window.location.origin}/dashboard/billing?checkout=success`,
          cancel_url: `${window.location.origin}/dashboard/billing?checkout=cancelled`,
        },
        token
      );
      window.location.href = checkout_url;
    } catch (err) {
      if (err instanceof ApiError && err.code === "billing_not_configured") {
        setNotConfiguredNotice(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not start checkout.");
      }
    } finally {
      setUpgradingPlanKey(null);
    }
  };

  if (isLoadingBusinesses) {
    return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  }

  if (!primaryBusiness || !token) {
    return <ComingSoon title="Billing" description="Create a business to see plans and billing here." />;
  }

  return (
    <div>
      <div className={styles.header}>
        <div className={styles.headerText}>
          <h1>Billing</h1>
          <p className={styles.subtitle}>Your plan and usage limits for this business.</p>
        </div>
      </div>

      {error && <p className={styles.error}>{error}</p>}
      {notConfiguredNotice && (
        <p className={styles.notice}>
          Billing isn&apos;t configured on this server yet. An administrator needs to set up Stripe
          before upgrades are available.
        </p>
      )}

      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : (
        <>
          {subscription && (
            <div className={styles.currentPlanCard}>
              <div className={styles.iconWrap}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <rect x="2" y="5" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M2 10h20" stroke="currentColor" strokeWidth="1.6" />
                </svg>
              </div>
              <div>
                <span className={styles.currentPlanLabel}>Current plan</span>
                <div className={styles.currentPlanNameRow}>
                  <span className={styles.currentPlanName}>{subscription.plan.name}</span>
                  <span className={styles.currentPlanStatus}>{subscription.status}</span>
                </div>
              </div>
            </div>
          )}

          <div className={styles.grid}>
            {plans.map((plan) => {
              const isCurrent = subscription?.plan.key === plan.key;
              return (
                <div key={plan.id} className={`${styles.planCard} ${isCurrent ? styles.planCardCurrent : ""}`}>
                  <h2 className={styles.planName}>{plan.name}</h2>
                  <p className={styles.planPrice}>{formatPrice(plan.price_ngn)}</p>
                  <ul className={styles.planLimits}>
                    <li>
                      <CheckIcon />
                      {limitText(plan.max_businesses_per_user, "business", "businesses")}
                    </li>
                    <li>
                      <CheckIcon />
                      {limitText(plan.max_branches_per_business, "branch", "branches")} per business
                    </li>
                    <li>
                      <CheckIcon />
                      {limitText(plan.max_team_members_per_business, "team member", "team members")}
                    </li>
                    <li>
                      <CheckIcon />
                      {limitText(plan.max_transactions_per_month, "transaction", "transactions")}/month
                    </li>
                  </ul>
                  {isCurrent ? (
                    <span className={styles.currentBadge}>Current plan</span>
                  ) : (
                    canManageBilling && (
                      <button
                        onClick={() => handleUpgrade(plan.key)}
                        disabled={upgradingPlanKey === plan.key}
                        className={styles.button}
                      >
                        {upgradingPlanKey === plan.key ? "Starting…" : "Choose plan"}
                      </button>
                    )
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

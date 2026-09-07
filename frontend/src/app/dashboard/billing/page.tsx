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
 */
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useDashboard } from "@/context/DashboardContext";
import { ApiError } from "@/lib/api";
import { getSubscription, listPlans, startCheckout } from "@/lib/billing";
import type { Plan, Subscription } from "@/types";
import ComingSoon from "@/components/ComingSoon";
import styles from "./billing.module.css";

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
        <h1>Billing</h1>
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
            <div className={styles.currentPlan}>
              <span className={styles.currentPlanLabel}>Current plan</span>
              <span className={styles.currentPlanName}>{subscription.plan.name}</span>
              <span className={styles.currentPlanStatus}>{subscription.status}</span>
            </div>
          )}

          <div className={styles.grid}>
            {plans.map((plan) => {
              const isCurrent = subscription?.plan.key === plan.key;
              return (
                <div key={plan.id} className={styles.planCard}>
                  <h2 className={styles.planName}>{plan.name}</h2>
                  <p className={styles.planPrice}>
                    {Number(plan.price_ngn) === 0 ? "Free" : `₦${plan.price_ngn}/mo`}
                  </p>
                  <ul className={styles.planLimits}>
                    <li>
                      {plan.max_businesses_per_user ?? "Unlimited"} business
                      {plan.max_businesses_per_user === 1 ? "" : "es"}
                    </li>
                    <li>
                      {plan.max_branches_per_business ?? "Unlimited"} branch
                      {plan.max_branches_per_business === 1 ? "" : "es"} per business
                    </li>
                    <li>
                      {plan.max_team_members_per_business ?? "Unlimited"} team member
                      {plan.max_team_members_per_business === 1 ? "" : "s"}
                    </li>
                    <li>
                      {plan.max_transactions_per_month ?? "Unlimited"} transactions/month
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

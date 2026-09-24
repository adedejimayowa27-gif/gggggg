/**
 * Two-factor login (TOTP) API client -- Step 12, Batch 12.6. Mirrors
 * the /auth/2fa/* routes added to backend/app/api/routes/auth.py.
 *
 * Login itself (POST /auth/login, POST /auth/2fa/verify-login) is
 * handled inside context/AuthContext.tsx, not here -- these are the
 * account-settings-side actions (enroll, disable, regenerate codes),
 * called from app/dashboard/account/page.tsx.
 */
import { apiFetch } from "@/lib/api";
import type { TwoFactorEnableResult, TwoFactorSetup } from "@/types";

export function setupTwoFactor(token: string): Promise<TwoFactorSetup> {
  return apiFetch("/auth/2fa/setup", { method: "POST", authToken: token });
}

export function enableTwoFactor(code: string, token: string): Promise<TwoFactorEnableResult> {
  return apiFetch("/auth/2fa/enable", {
    method: "POST",
    authToken: token,
    body: JSON.stringify({ code }),
  });
}

export function disableTwoFactor(password: string, code: string, token: string): Promise<{ message: string }> {
  return apiFetch("/auth/2fa/disable", {
    method: "POST",
    authToken: token,
    body: JSON.stringify({ password, code }),
  });
}

export function regenerateRecoveryCodes(
  password: string,
  code: string,
  token: string
): Promise<TwoFactorEnableResult> {
  return apiFetch("/auth/2fa/recovery-codes", {
    method: "POST",
    authToken: token,
    body: JSON.stringify({ password, code }),
  });
}

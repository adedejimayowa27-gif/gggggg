"use client";

/**
 * Auth context.
 *
 * Batch 12.3 -- real sessions. Two tokens now live here:
 *  - access_token: short-lived (15 min default -- see
 *    ACCESS_TOKEN_EXPIRE_MINUTES in backend/app/core/config.py), sent as
 *    the Authorization header on every API call, same as before.
 *  - refresh_token: long-lived and revocable (backend/app/models/refresh_token.py),
 *    used ONLY to fetch a new access_token via POST /auth/refresh, and
 *    to end the session for real via POST /auth/logout. Components never
 *    need it directly -- it lives in a ref, not in React state, so it
 *    never appears in a render.
 *
 * Both are still kept in localStorage (so a page refresh doesn't log the
 * user out), same as the pre-12.3 single token was.
 *
 * Proactive refresh: shortly before the access token expires, this
 * schedules a call to /auth/refresh on its own, so a user actively using
 * the app never sees a 401 from an expired access token. See
 * scheduleRefresh() below. Known limitation: this file does not react to
 * refresh calls made by OTHER browser tabs on the same account -- each
 * tab schedules its own refresh independently. Since refreshing rotates
 * the refresh token (the old one stops working), two tabs racing to
 * refresh at the same moment is possible but unlikely in practice (the
 * 60-second buffer before expiry is what a single tab needs, not what
 * two tabs would collide on); a full multi-tab sync (e.g. a
 * BroadcastChannel that shares the latest tokens across tabs) is a
 * bigger change, not part of this batch.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { msUntilExpiry } from "@/lib/jwt";
import type { AuthResponse, TwoFactorChallenge, User } from "@/types";

const TOKEN_STORAGE_KEY = "bizintel_token";
const REFRESH_TOKEN_STORAGE_KEY = "bizintel_refresh_token";

// Refresh this long before the access token's real expiry, so a slow
// request started just before expiry still completes with a valid token.
const REFRESH_BUFFER_MS = 60_000;
// Never schedule a refresh sooner than this, even if the token is
// already within the buffer window -- avoids a tight retry loop if
// something is briefly off (e.g. the device's clock).
const MIN_REFRESH_DELAY_MS = 5_000;

interface AuthContextValue {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  signup: (email: string, password: string, fullName?: string) => Promise<void>;
  // Batch 12.6: resolves to { twoFactorRequired: true, challengeToken }
  // instead of logging in directly when the account has 2FA enabled --
  // the caller (app/login/page.tsx) is responsible for then prompting
  // for a code and calling verifyTwoFactorLogin with it.
  login: (
    email: string,
    password: string
  ) => Promise<{ twoFactorRequired: false } | { twoFactorRequired: true; challengeToken: string }>;
  verifyTwoFactorLogin: (challengeToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Batch 12.2: re-fetches /auth/me, e.g. right after the user confirms
   * their email on the verify-email page, so the banner clears without
   * needing a full page reload. */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  // Refs, not state: the refresh token and the pending timer are never
  // read during render, only inside callbacks -- keeping them out of
  // state avoids re-rendering the whole app on every silent rotation.
  const refreshTokenRef = useRef<string | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearScheduledRefresh = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const clearSession = useCallback(() => {
    clearScheduledRefresh();
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    refreshTokenRef.current = null;
    setToken(null);
    setUser(null);
  }, [clearScheduledRefresh]);

  // Forward-declared via ref so scheduleRefresh (defined above it needs
  // to exist) and applyAuthResponse (which schedules the *next* refresh)
  // can call each other without a circular definition order problem.
  const performScheduledRefreshRef = useRef<() => Promise<void>>(async () => {});

  const scheduleRefresh = useCallback(
    (accessToken: string) => {
      clearScheduledRefresh();
      const remaining = msUntilExpiry(accessToken);
      // Token has no readable exp, or the refresh flow is unavailable for
      // this session (shouldn't happen once logged in) -- nothing to schedule.
      if (remaining === null) return;
      const delay = Math.max(remaining - REFRESH_BUFFER_MS, MIN_REFRESH_DELAY_MS);
      refreshTimerRef.current = setTimeout(() => {
        void performScheduledRefreshRef.current();
      }, delay);
    },
    [clearScheduledRefresh]
  );

  const applyAuthResponse = useCallback(
    (data: AuthResponse) => {
      localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token);
      localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, data.refresh_token);
      refreshTokenRef.current = data.refresh_token;
      setToken(data.access_token);
      setUser(data.user);
      scheduleRefresh(data.access_token);
    },
    [scheduleRefresh]
  );

  const exchangeRefreshToken = useCallback(
    async (refreshTokenValue: string): Promise<boolean> => {
      try {
        const data = await apiFetch<AuthResponse>("/auth/refresh", {
          method: "POST",
          body: JSON.stringify({ refresh_token: refreshTokenValue }),
        });
        applyAuthResponse(data);
        return true;
      } catch {
        // Expired, already used (rotated), or revoked (logout elsewhere,
        // a password reset, or reuse detection) -- either way, this
        // session is over. Clearing here (rather than throwing) is what
        // lets both the mount-time fallback and the proactive timer
        // below share this one function.
        clearSession();
        return false;
      }
    },
    [applyAuthResponse, clearSession]
  );

  useEffect(() => {
    performScheduledRefreshRef.current = async () => {
      if (refreshTokenRef.current) {
        await exchangeRefreshToken(refreshTokenRef.current);
      }
    };
  }, [exchangeRefreshToken]);

  useEffect(() => {
    const storedAccessToken = localStorage.getItem(TOKEN_STORAGE_KEY);
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);

    if (!storedAccessToken || !storedRefreshToken) {
      setIsLoading(false);
      return;
    }
    refreshTokenRef.current = storedRefreshToken;

    // Fast path: the access token from last time might still be valid,
    // which avoids rotating the refresh token (and the multi-tab
    // collision risk that comes with it -- see this file's module
    // comment) on every single page load.
    apiFetch<User>("/auth/me", { authToken: storedAccessToken })
      .then((currentUser) => {
        setToken(storedAccessToken);
        setUser(currentUser);
        scheduleRefresh(storedAccessToken);
      })
      .catch(async (err) => {
        // Only fall back to a refresh for an expired/invalid access
        // token specifically (401) -- a network error or a 5xx
        // shouldn't silently burn a rotation.
        if (err instanceof ApiError && err.status === 401) {
          await exchangeRefreshToken(storedRefreshToken);
        } else {
          clearSession();
        }
      })
      .finally(() => setIsLoading(false));
    // Runs once on mount only -- intentionally not re-run when the
    // functions above are re-created.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signup = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const data = await apiFetch<AuthResponse>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName || undefined }),
      });
      applyAuthResponse(data);
    },
    [applyAuthResponse]
  );

  const login = useCallback(
    async (email: string, password: string) => {
      // POST /auth/login returns either a normal AuthResponse or, when
      // the account has 2FA enabled, a TwoFactorChallenge instead --
      // see that type's comment. Neither shape is an error, so this
      // isn't a try/catch: a wrong password is still a thrown ApiError,
      // same as before.
      const data = await apiFetch<AuthResponse | TwoFactorChallenge>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if ("two_factor_required" in data) {
        return { twoFactorRequired: true as const, challengeToken: data.challenge_token };
      }
      applyAuthResponse(data);
      return { twoFactorRequired: false as const };
    },
    [applyAuthResponse]
  );

  const verifyTwoFactorLogin = useCallback(
    async (challengeToken: string, code: string) => {
      const data = await apiFetch<AuthResponse>("/auth/2fa/verify-login", {
        method: "POST",
        body: JSON.stringify({ challenge_token: challengeToken, code }),
      });
      applyAuthResponse(data);
    },
    [applyAuthResponse]
  );

  const logout = useCallback(async () => {
    if (token) {
      try {
        // Sending refresh_token is what actually revokes the session
        // server-side now (Batch 12.3) -- without it, the backend still
        // accepts the call (for older clients) but has nothing to revoke.
        // No `body` at all (not even `{}`) when there's no refresh token
        // to send: the backend's `payload` parameter only accepts a
        // full, valid RefreshTokenRequest or a genuinely bodyless
        // request -- an empty object would fail validation.
        await apiFetch("/auth/logout", {
          method: "POST",
          authToken: token,
          ...(refreshTokenRef.current
            ? { body: JSON.stringify({ refresh_token: refreshTokenRef.current }) }
            : {}),
        });
      } catch {
        // Even if the server call fails, proceed with local logout --
        // the user should never be stuck unable to leave their session.
      }
    }
    clearSession();
    router.push("/login");
  }, [token, clearSession, router]);

  const refreshUser = useCallback(async () => {
    if (!token) return;
    try {
      const currentUser = await apiFetch<User>("/auth/me", { authToken: token });
      setUser(currentUser);
    } catch {
      // A stale/expired token here is already handled by the proactive
      // refresh timer or the next authenticated call; this is best-effort.
    }
  }, [token]);

  useEffect(() => clearScheduledRefresh, [clearScheduledRefresh]);

  return (
    <AuthContext.Provider
      value={{ user, token, isLoading, signup, login, verifyTwoFactorLogin, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

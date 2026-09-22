/**
 * Decodes a JWT's payload WITHOUT verifying its signature. Never use
 * this to trust anything about the token's contents -- the backend
 * verifies the signature on every request that matters. This is only
 * for reading the `exp` claim client-side, to schedule a proactive
 * token refresh a little before the access token actually expires (see
 * AuthContext.tsx).
 */
export function decodeJwtPayload(token: string): { exp?: number; sub?: string } | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    // JWTs use base64url (- and _ instead of + and /, no padding).
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/").padEnd(payload.length + ((4 - (payload.length % 4)) % 4), "=");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

/** Milliseconds until the token's `exp` claim, or null if it can't be read. */
export function msUntilExpiry(token: string): number | null {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000 - Date.now();
}

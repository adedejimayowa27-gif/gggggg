/**
 * Step 12, Batch 12.1 -- security headers for every page the browser renders.
 *
 * The backend (app/core/security_headers.py) already sets protective headers
 * on API responses, but it never serves HTML, so it can't protect the pages
 * themselves. These headers do, and the Content-Security-Policy is the one
 * that matters most here: the login token lives in localStorage (see
 * src/context/AuthContext.tsx), so a script-injection bug would otherwise be
 * able to read it.
 *
 * Honest limits of this CSP:
 *  - script-src still allows 'unsafe-inline'. Next.js App Router injects small
 *    inline scripts for hydration, and a strict nonce-based policy needs a
 *    middleware that forces every page to render dynamically. That is a larger
 *    change, deliberately not part of this batch.
 *  - Everything else is locked down: no third-party scripts, styles, fonts or
 *    frames, no plugins, and network calls only to this site and the API.
 *
 * First deploy tip: set CSP_REPORT_ONLY=true to send the policy as
 * Content-Security-Policy-Report-Only. Browsers then log violations to the
 * console without blocking anything. Once the console is clean on every page
 * (landing, login, dashboard, settings), unset it to enforce.
 */
const isDev = process.env.NODE_ENV === "development";
const reportOnly = process.env.CSP_REPORT_ONLY === "true";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
let apiOrigin = "";
try {
  apiOrigin = new URL(apiUrl).origin;
} catch {
  // A malformed NEXT_PUBLIC_API_URL should not stop the build; the app itself
  // will fail loudly on its first API call instead.
}

const contentSecurityPolicy = [
  "default-src 'self'",
  // 'unsafe-eval' is only needed by React's dev tooling, never in production.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  // next/font downloads Google Fonts at build time and serves them from this
  // site, so no fonts.googleapis.com / fonts.gstatic.com origin is needed.
  "font-src 'self' data:",
  "img-src 'self' data: blob:",
  `connect-src 'self' ${apiOrigin}${isDev ? " ws: wss:" : ""}`.trim(),
  "manifest-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  {
    key: reportOnly ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy",
    value: contentSecurityPolicy,
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
  // HSTS only in production: it is meaningless (and confusing to debug) over
  // plain http://localhost during development.
  ...(isDev
    ? []
    : [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]),
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Don't advertise the framework in an "X-Powered-By: Next.js" header.
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;

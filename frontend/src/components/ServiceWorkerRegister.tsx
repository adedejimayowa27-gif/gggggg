"use client";

import { useEffect } from "react";

/**
 * Registers public/sw.js on mount. A no-op component (renders nothing)
 * included once in the root layout -- kept separate from layout.tsx
 * itself since registering a service worker needs browser APIs
 * (navigator.serviceWorker) that only exist in a Client Component,
 * while the rest of layout.tsx stays a Server Component.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Registration failing (unsupported browser, blocked by an
        // extension, etc.) should never break the app itself -- the
        // service worker is a progressive enhancement, not a
        // requirement for anything to function.
      });
    }
  }, []);

  return null;
}

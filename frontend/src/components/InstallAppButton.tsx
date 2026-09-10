"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./InstallAppButton.module.css";

/**
 * Not yet part of TypeScript's standard DOM lib types -- Chrome/Edge
 * fire this non-standard event before showing their own install UI;
 * calling preventDefault() suppresses that default UI so this button
 * can trigger the same native prompt on demand instead.
 */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari's own (non-standard, but real) flag for an already-
    // installed home-screen app -- display-mode media query support for
    // standalone detection is inconsistent enough on iOS that this is
    // the more reliable check there specifically.
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

/**
 * Renders nothing until the browser actually offers an install prompt
 * (most browsers never fire this -- Safari/iOS and Firefox desktop
 * notably don't support beforeinstallprompt at all) and disappears
 * again the moment the app is installed. There is deliberately no
 * fallback "how to install" instructions for unsupported browsers here
 * -- a button that's sometimes real and sometimes just explanatory text
 * would be confusing about what tapping it actually does.
 */
export default function InstallAppButton({ className }: { className?: string }) {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    setIsInstalled(isStandalone());

    const handleBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as BeforeInstallPromptEvent);
    };
    const handleAppInstalled = () => {
      setIsInstalled(true);
      setInstallEvent(null);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
    };
  }, []);

  const handleInstall = useCallback(async () => {
    if (!installEvent) return;
    await installEvent.prompt();
    // A captured prompt can only be used once regardless of the
    // person's choice -- cleared either way so a re-render doesn't try
    // to reuse a spent event.
    await installEvent.userChoice;
    setInstallEvent(null);
  }, [installEvent]);

  if (isInstalled || !installEvent) return null;

  return (
    <button className={`${styles.button} ${className ?? ""}`} onClick={handleInstall}>
      Install app
    </button>
  );
}

import type { MetadataRoute } from "next";

/**
 * Next.js's native app/manifest.ts convention -- this generates
 * /manifest.webmanifest automatically, and Next.js's metadata resolution
 * automatically injects the <link rel="manifest"> tag into every page's
 * <head>, so nothing else needs to reference this file directly.
 *
 * `display: "standalone"` (no browser chrome once installed) plus a real
 * icon set is what makes Chrome/Edge treat this as installable and offer
 * the native install prompt that InstallAppButton.tsx listens for.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Mayorcity Bizintel",
    short_name: "Bizintel",
    description:
      "See exactly where your business stands -- clear analytics, what-if simulations, and early warnings, built from the sales data you already keep.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#10140F",
    theme_color: "#10140F",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

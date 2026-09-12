import type { Metadata, Viewport } from "next";
import { Manrope, Space_Grotesk, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
});

// Loaded specifically for the dashboard product UI (see .dashboardTheme in
// globals.css) -- kept separate from Manrope (marketing/auth pages) rather
// than replacing the whole site's type system, since the dashboard redesign
// brief calls for a cleaner, more neutral workhorse face at data-dense
// screens while the marketing site keeps its own distinct voice.
const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-plus-jakarta",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Mayorcity Bizintel — clarity for your business, from the numbers you already have",
  description:
    "Import your sales from Excel, CSV, Google Sheets, or OneDrive and see exactly where your business stands -- clear analytics, what-if simulations, and early warnings before small problems become big ones.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    // iOS ignores the web manifest for "Add to Home Screen" -- these are
    // the equivalent Apple-specific tags that make it install as a
    // standalone app there too, with its own name and icon.
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Bizintel",
  },
  icons: {
    icon: "/icons/icon-192.png",
    apple: "/icons/icon-192.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#10140F",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${manrope.variable} ${plusJakarta.variable}`}>
      <body>
        <AuthProvider>{children}</AuthProvider>
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}

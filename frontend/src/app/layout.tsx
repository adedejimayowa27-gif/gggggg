import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BizIntel — AI Business Intelligence for SMBs",
  description:
    "Understand your business, forecast the future, and simulate decisions before you make them.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

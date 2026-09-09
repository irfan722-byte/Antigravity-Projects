import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = {
  title: "AurumGuard",
  description: "XAU/USD rule-based analysis, risk management and paper trading. Not investment advice.",
  manifest: "/manifest.webmanifest",
  applicationName: "AurumGuard",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "AurumGuard" },
  icons: { icon: "/icons/icon.svg", apple: "/icons/icon-192.png" },
};
export const viewport: Viewport = { themeColor: "#b8860b", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      {/* Browser extensions add attributes to <body> before React hydrates (password managers,
          accessibility and analytics tools). suppressHydrationWarning on <html> does not cover a
          child element, so the mismatch surfaced as a console error in dev. It suppresses the
          warning for this element's own attributes only; real mismatches inside the app still report. */}
      <body suppressHydrationWarning><a href="#main" className="sr-only">Skip to content</a><Providers>{children}</Providers></body>
    </html>
  );
}

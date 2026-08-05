import type { Metadata, Viewport } from "next";
import { Fraunces, Karla, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  style: ["normal", "italic"],
});

const karla = Karla({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "600"],
});

const siteTitle = "Masterji — the coach who makes you ship";
const siteDescription =
  "A tough-love AI execution coach for first-time builders. One goal, " +
  "earned phases, daily proof — no hiding in planning.";

export const metadata: Metadata = {
  title: siteTitle,
  description: siteDescription,
  openGraph: { title: siteTitle, description: siteDescription, type: "website" },
};

export const viewport: Viewport = {
  themeColor: "#10151A",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${karla.variable} ${jetbrainsMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}

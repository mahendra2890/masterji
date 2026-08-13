import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import "./globals.css";

// These three were `next/font/google` until the fonts took a deploy down.
// That helper fetches the files from Google *during the build* and inlines
// them; when the fetch fails the generated CSS keeps an unresolvable
// `@vercel/turbopack-next/internal/font/google/font` specifier, and the build
// dies with one "Module not found" per @font-face — eleven of them, on a commit
// that only added a markdown file. Nothing about the app was wrong and a retry
// passed, which is the problem: it can fail again on any commit, including one
// going to production.
//
// The files are now in the repo, so a build needs no network at all. They are
// the same variable woff2 files Google was serving, latin subset only — which
// is deliberately unchanged from `subsets: ["latin"]`: the Devanagari in
// "मास्टरजी" was never covered by these fonts and still falls back to a system
// face. Weight ranges cover exactly the weights that were requested before.
//
// Refreshing them means re-fetching from the Google CSS API and replacing the
// four files; nothing here reaches out on its own, so a new Fraunces upstream
// will not arrive by surprise.
const fraunces = localFont({
  variable: "--font-display",
  display: "swap",
  src: [
    {
      path: "./fonts/fraunces-latin-var.woff2",
      weight: "500 700",
      style: "normal",
    },
    {
      path: "./fonts/fraunces-latin-var-italic.woff2",
      weight: "500 700",
      style: "italic",
    },
  ],
});

const karla = localFont({
  variable: "--font-body",
  display: "swap",
  src: [
    {
      path: "./fonts/karla-latin-var.woff2",
      weight: "400 700",
      style: "normal",
    },
  ],
});

const jetbrainsMono = localFont({
  variable: "--font-mono",
  display: "swap",
  src: [
    {
      path: "./fonts/jetbrains-mono-latin-var.woff2",
      weight: "400 600",
      style: "normal",
    },
  ],
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
      <body>
        {children}
        {/* Both were already switched on in the Vercel dashboard and reporting
            nothing, because the numbers come from these scripts and not from
            the platform — without them the pages read 0 visitors forever.
            Cookieless and no cross-site identity, so neither needs a consent
            banner, and this app has only three paths (/, /demo, /waking) with
            no dynamic segments, so a pathname can't name a builder.

            Page views only: custom events are a Pro feature, so the counts
            that would actually be worth having — proofs filed, gates passed —
            still have to come from the server's own rows. */}
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}

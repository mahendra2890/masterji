import type { MetadataRoute } from "next";

import { SITE_DESCRIPTION, SITE_NAME, SITE_TITLE, THEME_COLOR } from "./site";

/* What makes this app installable, and what it deliberately does not ship.
 *
 * The whole retention mechanism here is "come back tonight", and until now the
 * only hook was the builder remembering a browser tab. This is the icon on the
 * home screen — the cheapest thing in the product that competes with WhatsApp
 * for a thumb.
 *
 * **There is no service worker, and that is the current answer rather than a
 * shortcut.** Chrome dropped the service-worker requirement for installing
 * from the menu in version 108 on mobile and 112 on desktop; only the
 * automatic install *banner* still looks for a `fetch()` handler, and Chrome
 * has said it is removing that too. Its stated reason for the change is the
 * exact thing we would otherwise be doing: sites were shipping empty fetch
 * handlers purely to satisfy the check. On iOS none of it applies — Safari has
 * offered Add to Home Screen since 16.4 with no manifest requirement at all,
 * and reads this file only to decide how the installed window looks.
 *
 * So the honest version of "no service worker logic beyond the install
 * requirement" is none. The thing a worker would actually buy is offline, and
 * offline is a real feature with a real cost — a cached shell that outlives a
 * deploy is how an installed app pins itself to a build from last Tuesday. If
 * this product ever wants offline, it should want it on purpose.
 *
 * Icons are PNG rather than the SVG they were drawn from, on purpose: the mark
 * is म, and the Devanagari in this product has never been covered by a font
 * the repo ships (see the note on the fonts in app/layout.tsx). A rasterised
 * glyph carries itself; an SVG one would render as a box on any machine
 * without a Devanagari face. Source and the command that made them are in
 * docs/brand/.
 */
export function appManifest(): MetadataRoute.Manifest {
  return {
    /* `id` pins the install's identity. Without it the identity IS start_url,
       so moving the landing page later would read as a different app and the
       icon already on a home screen would be orphaned. */
    id: "/",
    name: SITE_TITLE,
    /* What fits under an icon. Android truncates around 12 characters, and
       the wordmark is the half a builder would recognise anyway. */
    short_name: SITE_NAME,
    description: SITE_DESCRIPTION,
    start_url: "/",
    scope: "/",
    /* No browser chrome. The app is a daily loop with its own header; an
       address bar over it is a reminder that this is a tab. */
    display: "standalone",
    /* Deliberately no `orientation` lock: this installs on a laptop too, and
       pinning a desktop window to portrait is a worse bargain than anything a
       lock would buy on a phone. */
    background_color: THEME_COLOR,
    theme_color: THEME_COLOR,
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      /* Android crops an icon to whatever shape the launcher uses, so the
         maskable copy carries the same mark smaller, inside the safe circle.
         Without it the launcher pads the square one and the result is a small
         glyph in a grey tile. */
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

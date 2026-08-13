import type { MetadataRoute } from "next";

import { appManifest } from "@/lib/manifest";

/* Next's file convention: this route becomes /manifest.webmanifest and the
   framework adds the <link rel="manifest"> to every page, so nothing in
   layout.tsx has to remember to.

   The manifest itself lives in lib/ with the rest of the logic this repo
   tests — a static public/manifest.json would have been fewer lines and no
   way to assert that the icons it names exist. */
export default function manifest(): MetadataRoute.Manifest {
  return appManifest();
}

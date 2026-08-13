import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { appManifest } from "./manifest";
import { THEME_COLOR } from "./site";

const PUBLIC_DIR = join(__dirname, "..", "public");

/** Width and height out of a PNG's IHDR — bytes 16..24, big-endian.
 *
 *  The manifest states a `sizes` string for every icon and nothing in the
 *  toolchain checks it against the file. A wrong one is silent: Chrome looks
 *  for a 192 and a 512, believes the string, and the install either offers a
 *  blurry icon or does not qualify at all. So read the real pixels. */
function pngSize(file: string): { width: number; height: number } {
  const buf = readFileSync(file);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

describe("the install manifest", () => {
  const manifest = appManifest();

  /* Chromium's stated bar, from MDN's installability list: a name, icons at
     192 and 512, a start_url, and a display mode. These four are what make
     the difference between "a website you can bookmark" and an entry in the
     app drawer, which is the whole of what this ships. */
  it("carries the fields an install is judged on", () => {
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
  });

  it("keeps a stable identity so an install survives a moved start_url", () => {
    expect(manifest.id).toBe("/");
  });

  it("offers 192 and 512, and one icon Android may crop to its own shape", () => {
    const icons = manifest.icons ?? [];
    const sizes = icons.map((i) => i.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
    expect(icons.some((i) => i.purpose === "maskable")).toBe(true);
    expect(icons.every((i) => i.type === "image/png")).toBe(true);
  });

  /* The failure this exists for: a manifest that names a file nobody shipped.
     It costs nothing to state an icon and everything to state a missing one —
     the install silently stops qualifying and no build step complains. */
  it("names icons that are actually in public/, at the sizes it claims", () => {
    for (const icon of manifest.icons ?? []) {
      const file = join(PUBLIC_DIR, icon.src.replace(/^\//, ""));
      const [w, h] = String(icon.sizes).split("x").map(Number);
      expect(pngSize(file)).toEqual({ width: w, height: h });
    }
  });

  /* The installed window paints its chrome with theme_color and its splash
     with background_color. Both are the app's own background, and the copy
     that matters is the one in globals.css — if they drift, the standalone
     window gets a seam the browser tab never had. */
  it("paints the standalone window the colour the app already is", () => {
    const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");
    const bg = css.match(/--bg:\s*(#[0-9a-fA-F]{6})/)?.[1];

    expect(bg?.toLowerCase()).toBe(THEME_COLOR.toLowerCase());
    expect(manifest.theme_color).toBe(THEME_COLOR);
    expect(manifest.background_color).toBe(THEME_COLOR);
  });
});

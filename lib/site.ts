/* The handful of strings and the one colour that more than one surface has to
   agree on.

   They were literals in app/layout.tsx, which was correct while the document
   head was the only thing that needed them. The install manifest needs the
   same name and the same colour, and a manifest that disagrees with the page
   is not a cosmetic problem: the name is what sits under the icon on a home
   screen, and the colour is what the installed window paints its own chrome
   with. A second copy is how those quietly stop matching.

   THEME_COLOR is the one to be careful with — it is `--bg` in
   app/globals.css, copied here because CSS custom properties are not readable
   from the metadata export. lib/manifest.test.ts reads globals.css and fails
   if the two ever part company. */

export const SITE_NAME = "Masterji";

export const SITE_TITLE = "Masterji — the coach who makes you ship";

export const SITE_DESCRIPTION =
  "A tough-love AI execution coach for first-time builders. One goal, " +
  "earned phases, daily proof — no hiding in planning.";

/** `--bg` in app/globals.css. Chalkboard dark. */
export const THEME_COLOR = "#10151a";

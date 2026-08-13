import { describe, expect, it } from "vitest";
import { filenameFrom } from "./download";

/** What these protect: the export's filename is the server's to choose, and this
 * is the one step between that header and the browser writing a file. Goal
 * titles are free text, so the header is not fully trusted even though this
 * repo wrote both ends of it. */
describe("filenameFrom", () => {
  it("takes the name the server sent", () => {
    expect(
      filenameFrom(
        'attachment; filename="masterji-tiffin-app-2026-08-13.md"',
        "fallback.md",
      ),
    ).toBe("masterji-tiffin-app-2026-08-13.md");
  });

  it("keeps only the last path segment", () => {
    // The server slugs titles, so a separator should never arrive — but a
    // filename is handed straight to the browser's writer, and this is the last
    // place it can be checked.
    expect(
      filenameFrom('attachment; filename="../../etc/passwd"', "fallback.md"),
    ).toBe("passwd");
  });

  it("falls back when the header is missing, empty or unparseable", () => {
    // A proxy that strips the header, or an older API that never set it. A
    // download with a dull name beats a download with none.
    for (const header of [null, "", "attachment", 'attachment; filename=""']) {
      expect(filenameFrom(header, "fallback.md"), JSON.stringify(header)).toBe(
        "fallback.md",
      );
    }
  });
});

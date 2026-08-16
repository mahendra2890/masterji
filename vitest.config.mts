/** Vitest had no config at all until the record's paging needed one.
 *
 * Every existing test is over a leaf module — `lib/day`, `lib/record`,
 * `lib/gate` — and none of those import anything by the `@/` alias, so the
 * default resolution was enough. `lib/coach-api` is the first tested module
 * that does (`@/lib/auth-client`, for `API_URL`), and without the alias its
 * suite fails to import rather than fails to pass.
 *
 * One line, mirroring `tsconfig.json`'s `paths`. Adding it here rather than
 * rewriting the import in `coach-api`: the alias is how the rest of the app
 * refers to itself, and the test runner is the thing that was out of step.
 */
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
});

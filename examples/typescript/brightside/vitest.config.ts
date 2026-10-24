// The tutor, run with no network, no key and no model: the class loads, its macro is checked.
//
// The decorator settings are the framework's own, repeated for vitest's oxc transform as Clínica
// Norte's config repeats them.
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: {
    decorator: { legacy: true },
    jsx: { runtime: "automatic", importSource: "@pinecall/agents/views" },
  },
  test: {
    include: ["agents/*/test/**/*.test.ts"],
  },
});

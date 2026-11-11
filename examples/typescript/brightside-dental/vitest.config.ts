// The app, run against the fake gateway: no network, no key, no model. The decorator and JSX settings are the
// framework's own, repeated here because vitest's transform reads no tsconfig (../clinica-norte/vitest.config.ts).
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: {
    decorator: { legacy: true },
    jsx: { runtime: "automatic", importSource: "@pinecall/agents/views" },
  },
  test: {
    include: ["test/**/*.test.ts", "agents/*/test/**/*.test.ts"],
  },
});

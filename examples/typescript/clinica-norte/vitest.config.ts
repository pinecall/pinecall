// The tenant, run against the fake gateway: no network, no key, no model.
//
// The decorator and JSX settings are the framework's own — a tenant writing `@tool` and a `.tsx`
// view needs the same toolchain flags the package is written against, and gets them from
// @pinecall/agents/tsconfig.tenant.json. Vitest reads none of that: its transform is oxc's, so the same
// two facts are repeated here until oxc can read a tsconfig (docs/decisions/agent.md).
//
// Nothing is aliased. This example resolves `@pinecall/agents` exactly as a customer does, through
// node_modules; the package's exports lead to its sources here and to its dist from npm.
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: {
    decorator: { legacy: true },
    jsx: { runtime: "automatic", importSource: "@pinecall/agents/views" },
  },
  test: {
    include: ["agents/*/test/**/*.test.ts", "agents/*/test/**/*.test.tsx"],
  },
});

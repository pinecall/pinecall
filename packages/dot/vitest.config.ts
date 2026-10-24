/** The suite: the wire, the macro player and the agent's side in node; the face, the page, the pointer and the tutor on happy-dom. */

import { configDefaults, defineConfig } from "vitest/config";

// Two environments, split by directory: everything that needs a document lives under the directory
// of the part it tests; everything else runs in node, where a `document` reached by accident is a
// failure and not a silent pass.
const DOM = ["test/face/**/*.test.ts", "test/page/**/*.test.ts", "test/pointer/**/*.test.ts", "test/tutor/**/*.test.ts"];

// `Tutor`'s `@tool` is a legacy decorator, as @pinecall/agents' are; oxc is told so here, as the
// framework's own example tells it.
export default defineConfig({
  oxc: { decorator: { legacy: true } },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "dot",
          environment: "node",
          include: ["test/**/*.test.ts"],
          exclude: [...configDefaults.exclude, ...DOM],
        },
      },
      {
        extends: true,
        test: { name: "dom", environment: "happy-dom", include: DOM },
      },
    ],
  },
});

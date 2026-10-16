/** The suite: the room in node against a fake gateway and a fake LiveKit; the seat and React on happy-dom. */

import { configDefaults, defineConfig } from "vitest/config";

// Two environments, split by directory. Everything that needs a document — an audio element for
// the agent's voice, a React root — lives under test/seat or test/react; everything else runs in
// node, where a `document` reached by accident is a failure and not a silent pass.
const DOM = ["test/seat/**/*.test.ts", "test/react/**/*.test.ts"];

export default defineConfig({
  test: {
    projects: [
      {
        test: {
          name: "room",
          environment: "node",
          include: ["test/**/*.test.ts"],
          exclude: [...configDefaults.exclude, ...DOM],
        },
      },
      {
        test: { name: "dom", environment: "happy-dom", include: DOM },
      },
    ],
  },
});

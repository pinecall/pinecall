/** The tenant's project: one agent per folder under agents/, and every path a verb reads inside it. */

import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { agentFilesOf, agentsOf, homeOf } from "../../src/project/layout.js";
import { project, write } from "../support/project.js";

describe("the layout", () => {
  it("finds one agent per folder, the first file name of the four that is there", () => {
    const root = project(["front-desk"]);
    write(root, "agents/sales/agent.rb", "");
    write(root, "agents/sales/agent.py", "");
    write(root, "agents/notes/README.md", "");
    expect(agentFilesOf(root).map((file) => file.slice(root.length + 1))).toEqual(["agents/front-desk/agent.ts", "agents/sales/agent.rb"]);
  });

  it("names every path a verb reads, all of them in the agent's own folder", () => {
    const root = project(["front-desk"]);
    const home = homeOf(join(root, "agents/front-desk/agent.ts"));
    const own = join(root, "agents/front-desk");
    expect(home).toMatchObject({
      name: "front-desk",
      root,
      docs: join(own, "docs"),
      goldens: join(own, "test/goldens"),
      docsGolden: join(own, "test/goldens/docs.json"),
      memoryGolden: join(own, "test/goldens/memory.json"),
      memoryCases: join(own, "test/memory"),
      personas: join(own, "test/personas"),
      candidates: join(own, "test/candidates"),
    });
  });

  it("every agent of the project, or the one named", () => {
    const root = project(["front-desk", "sales"]);
    expect(agentsOf(root).map((home) => home.name)).toEqual(["front-desk", "sales"]);
    expect(agentsOf(root, { agent: "sales" }).map((home) => home.name)).toEqual(["sales"]);
  });
});

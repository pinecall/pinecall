// Lifecycle hooks, where state may be assigned outside a tool.
import { describe, expect, it } from "vitest";

import { changes, runHook, seal } from "../../src/index.js";
import ClinicaNorte from "./clinica-norte.js";

describe("lifecycle", () => {
  it("authors a write inside onCall to the hook, not to nobody", async () => {
    const agent = seal(new ClinicaNorte());
    await runHook(agent, "onCall", { id: "c1", contact: "+34 600 000 001", from: "+34 600 000 001" });
    expect(changes(agent)).toHaveLength(1);
    expect(changes(agent)[0]).toMatchObject({ field: "patient", author: "hook:onCall" });
  });

  it("does nothing by default, and says nothing", async () => {
    const agent = seal(new ClinicaNorte());
    await runHook(agent, "onEnd", { id: "c1", contact: "+34 600 000 001" });
    await runHook(agent, "onMemory", [], { id: "c1", contact: "+34 600 000 001" });
    expect(changes(agent)).toHaveLength(0);
  });
});

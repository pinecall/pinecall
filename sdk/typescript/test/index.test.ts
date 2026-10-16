// Pins the public exports of `@pinecall/agents` so internals cannot leak onto the surface unnoticed.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import * as api from "../src/index.js";

// Sorted.
const PUBLIC = [
    "Agent",
    "CONFIG_FIELDS",
    "CallWorld",
    "DeclarationRefused",
    "Example",
    "Fragment",
    "History",
    "NO_GATEWAY_TO_SEARCH",
    "PROMPT_BLOCKS",
    "ParticipantHandle",
    "Protocols",
    "Room",
    "Rule",
    "Rules",
    "Section",
    "ToolFailed",
    "UnauthoredWrite",
    "accepts",
    "blocks",
    "changes",
    "classDoc",
    "collapse",
    "currentAuthor",
    "declaredStateOf",
    "describe",
    "diff",
    "docOf",
    "docsOf",
    "docsVersion",
    "emitEvent",
    "eventsOf",
    "headerFor",
    "improvise",
    "internalsOf",
    "isConfigField",
    "jsx",
    "jsxDEV",
    "jsxs",
    "judge",
    "llm",
    "logOf",
    "methodDoc",
    "methodParams",
    "mount",
    "onChange",
    "onLog",
    "optionsFor",
    "p",
    "parametersOf",
    "parseClassSource",
    "promptOf",
    "recalled",
    "register",
    "render",
    "renderInline",
    "renderToNodes",
    "renderToText",
    "restore",
    "runHook",
    "runTool",
    "said",
    "seal",
    "setCall",
    "setLast",
    "showPrompt",
    "slugOf",
    "snapshot",
    "state",
    "stt",
    "tagged",
    "tool",
    "toolNamed",
    "toolsOf",
    "view",
    "viewOf",
    "visibilityOf",
    "visibleTools",
    "visibleToolsOf",
    "voice",
    "withAuthor",
    "withAuthorAsync",
];

describe("the package's public surface", () => {
  it("exports these names and no others", () => {
    expect(Object.keys(api).sort()).toEqual(PUBLIC);
  });

  it("exports nothing from the CLI and nothing the bridge only talks to itself with", () => {
    const internals = ["absorb", "screenFor", "draw", "urlFrom", "apiKeyFrom", "load", "mountOptions", "inOrder", "dispatch", "validate", "argumentsFor", "preview", "connectedLine", "talk"];
    expect(internals.filter((name) => name in api)).toEqual([]);
  });
});

describe("what npm actually serves", () => {
  // Tenants resolve `publishConfig.exports`, this checkout `exports`; the two must list the same subpaths.
  it("publishes every subpath it develops against", () => {
    const pkg = JSON.parse(
      readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8"),
    ) as { exports: Record<string, unknown>; publishConfig: { exports: Record<string, unknown> } };
    expect(Object.keys(pkg.publishConfig.exports).sort()).toEqual(Object.keys(pkg.exports).sort());
  });
});

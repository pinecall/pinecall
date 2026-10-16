/** CONTRIBUTING.md as a suite: a file in the wrong place, a layer that imports upwards, a fetch outside api/ fails here, not in a review. */

import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { canon, docstrings, everyRule, gatewayAtHome, layers, mirrors, neverTheFramework, outputAtHome, size, sources, SRC, vocabulary } from "./rules.js";

const all = sources();
const tests = sources(resolve(SRC, "../test"));

describe("the twelve rules", () => {
  it("1. canon: a domain holds commands, service and render", () => expect(canon(all)).toEqual([]));
  it("2. layers: nothing imports upwards, nothing cycles", () => expect(layers(all)).toEqual([]));
  it("3. the gateway at home: fetch and /v1/ only in api/", () => expect(gatewayAtHome(all)).toEqual([]));
  it("4. output at home: streams only in kit/io; no exit; a service never prints", () => expect(outputAtHome(all)).toEqual([]));
  it("8. boring names: the banned words are not names of ours", () => expect(vocabulary(all)).toEqual([]));
  it("9. size: 400 lines a module, 150 at the top", () => expect(size(all)).toEqual([]));
  it("10. never the framework: client and wire alone, no port", () => expect(neverTheFramework(all)).toEqual([]));
  it("11. tests mirror the tree", () => expect(mirrors(tests, all)).toEqual([]));
  it("12. every file opens with one line saying what it is", () => expect(docstrings(all)).toEqual([]));
  it("reads the whole tree", () => expect(all.length).toBeGreaterThan(100));
  it("answers every rule at once", () => expect(Object.values(everyRule(all)).flat()).toEqual([]));
});

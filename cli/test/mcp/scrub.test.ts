/** No secret crosses a model: the session's own secrets and anything shaped like a Pinecall key hidden, but what a tool means to reveal. */

import { describe, expect, it } from "vitest";

import { HIDDEN, scrub } from "../../src/mcp/scrub.js";

describe("scrub", () => {
  it("hides the secrets it is given, and every Pinecall-shaped key or code", () => {
    expect(scrub("vendor sk-proj-abcdef and pc_live_0123456789 and pc_test_abcdefgh and lc_9f8e7d6c", ["sk-proj-abcdef"])).toBe(`vendor ${HIDDEN} and ${HIDDEN} and ${HIDDEN} and ${HIDDEN}`);
  });

  it("leaves a secret too short to be one, and what a tool reveals", () => {
    expect(scrub("abc pc_live_short1", ["abc"])).toBe(`abc ${HIDDEN}`);
    expect(scrub("open https://cloud.pinecall.io/?login=lc_onetimecode1 now", [], ["lc_onetimecode1"])).toBe("open https://cloud.pinecall.io/?login=lc_onetimecode1 now");
  });
});

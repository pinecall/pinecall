/** `pinecall setup` as typed: a project on another host's gateway is advised by that host, and this machine is left alone. */

import { describe, expect, it } from "vitest";

import { answer, GATEWAY } from "../support/gateway.js";
import { run } from "../support/run.js";

const ADVICE = {
  stages: [
    { stage: "stt", choice: "openai/deepdml/faster-whisper-large-v3-turbo-ct2", runs_on: "served here", served: ["deepdml/faster-whisper-large-v3-turbo-ct2"] },
    { stage: "llm", choice: "anthropic/claude-haiku-5-5", runs_on: "lent by the host", served: [] },
    { stage: "tts", choice: "cartesia", runs_on: "needs a key", served: [] },
  ],
  lends: ["anthropic"],
  judge: "anthropic/claude-haiku-5-5",
  caller: null,
  machine: null,
};

describe("pinecall setup on another host", () => {
  it("prints what that host advises, stage by stage, and where a missing key is; nothing of this machine", async () => {
    answer("get", "/v1/providers/advice", ADVICE);
    const ran = await run(["setup", "--recommend"], { env: { CARTESIA_API_KEY: "ck-secret" } });
    expect(ran.code).toBe(0);
    expect(ran.out).toContain(`this runtime  ${GATEWAY} · lends anthropic`);
    expect(ran.out).toMatch(/thinking\s+anthropic\/claude-haiku-5-5\s+lent by the host/);
    expect(ran.out).toMatch(/voice\s+cartesia\s+needs a key/);
    expect(ran.out).toContain("CARTESIA_API_KEY: in the environment");
    expect(ran.out).toContain("pinecall agent set --agent <name> --stt openai/deepdml/faster-whisper-large-v3-turbo-ct2 --llm anthropic/claude-haiku-5-5 --tts cartesia");
    expect(ran.out + ran.err).not.toContain("ck-secret");
  });

  it("answers the host's advice whole under --json", async () => {
    answer("get", "/v1/providers/advice", ADVICE);
    const ran = await run(["--json", "setup", "--recommend"]);
    expect(JSON.parse(ran.out)).toMatchObject({ url: GATEWAY, lends: ["anthropic"], stages: [{ stage: "stt", runsOn: "served here" }, {}, {}] });
  });
});

// A number is added the ways the box allows: buying only when it sells, the carriers its operator
// admits (Twilio automatic, the rest guided), an own PBX reviewed once, and WhatsApp. The list
// says where each number comes through and what a call to it does.

import { describe, expect, it } from "vitest";

import { type Answering, type Carrier, type Catalog } from "../src/screens/numbers/door.js";
import { RINGS_SAID, comesThrough, countRings, waysOffered } from "../src/screens/numbers/ways.js";

const CATALOG: Catalog = {
  carriers: [
    { kind: "twilio", name: "Twilio", how: "automatic", networks: [] },
    { kind: "telnyx", name: "Telnyx", how: "guided", networks: [] },
  ],
  sells: false,
};

const row = (changes: Partial<Answering> = {}): Answering => ({
  route: { org: "org_a", agent: "recepcion", channel: "phone", number: "+59829001199", label: null, env: "production", managed: false },
  origin: "imported",
  rings: "ok",
  last_call_at: null,
  via: null,
  account: null,
  ...changes,
});

const TWILIO: Carrier = { kind: "twilio", account: "AC1", label: "Clínica", networks: [] };

describe("adding a number", () => {
  it("offers the admitted carriers, a PBX and WhatsApp, and buying only when the box sells", () => {
    expect(waysOffered(CATALOG).map((way) => [way.id, way.how])).toEqual([
      ["twilio", "automatic"],
      ["via:telnyx", "guided"],
      ["pbx", "reviewed"],
      ["whatsapp", "automatic"],
    ]);
    expect(waysOffered({ ...CATALOG, sells: true })[0]?.id).toBe("buy");
  });

  it("says where each number comes through: bought, its account, a catalog carrier, the operator", () => {
    expect(comesThrough(row({ route: { ...row().route, managed: true } }), [], CATALOG).name).toBe("Pinecall");
    expect(comesThrough(row({ account: "AC1" }), [TWILIO], CATALOG)).toEqual({ name: "Twilio", sub: "Clínica · AC1" });
    expect(comesThrough(row({ origin: "hooked", via: "telnyx" }), [], CATALOG).name).toBe("Telnyx");
    expect(comesThrough(row({ origin: "typed" }), [], CATALOG).name).toBe("The box operator");
  });

  it("counts what a call to each number does, and says it in the list's words", () => {
    expect(countRings([row(), row({ rings: "waiting" }), row({ rings: "broken" }), row()])).toEqual({ ok: 2, waiting: 1, broken: 1 });
    expect(RINGS_SAID.broken.tone).toBe("red");
  });
});

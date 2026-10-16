/** A hosted app's row: its state in one line, its hours this month, how fresh its logs are. */

import { describe, expect, it } from "vitest";

import { firstLine, hours, readAgo, servedByApp, stateOf } from "../src/screens/apps/fold";

const AN_APP = { name: "clinica-norte", release: 3, live_release: 3, failed_why: null, stopped: false, created_by: "ana@clinica.uy", created_at: 1.5 };

describe("an app's state", () => {
  it("is live when the newest release is the one serving", () => {
    expect(stateOf(AN_APP)).toEqual({ text: "live · release 3", tone: "green", why: null });
  });

  it("is on its way while the newest is not serving yet, whatever serves meanwhile", () => {
    expect(stateOf({ ...AN_APP, live_release: 2 }).text).toBe("release 3 on its way");
    expect(stateOf({ ...AN_APP, live_release: null }).text).toBe("release 3 on its way");
  });

  it("is failed, with the whole reason kept, when the newest did not build or start", () => {
    const failed = stateOf({ ...AN_APP, live_release: 2, failed_why: "npm ci exited 1\nnpm ERR! missing lockfile" });
    expect(failed.text).toBe("release 3 failed");
    expect(failed.why).toBe("npm ci exited 1\nnpm ERR! missing lockfile");
    expect(firstLine(failed.why ?? "")).toBe("npm ci exited 1");
  });

  it("is stopped when a person stopped it, whatever its releases say", () => {
    expect(stateOf({ ...AN_APP, stopped: true, failed_why: "boom" }).text).toBe("stopped");
  });

  it("says so before its first release", () => {
    expect(stateOf({ ...AN_APP, release: null, live_release: null }).text).toBe("no release yet");
  });
});

describe("the time an app served", () => {
  it("sums its days, one app at a time, and reads in hours with one decimal", () => {
    const rows = [
      { org: "clinica", env: "production" as const, name: "a", day: "2026-09-01", seconds: 3600 },
      { org: "clinica", env: "production" as const, name: "a", day: "2026-09-02", seconds: 1800 },
      { org: "clinica", env: "production" as const, name: "b", day: "2026-09-02", seconds: 60 },
    ];
    const served = servedByApp(rows);
    expect(hours(served.get("a") ?? 0)).toBe("1.5 h");
    expect(hours(served.get("b") ?? 0)).toBe("0.0 h");
    expect(served.has("c")).toBe(false);
  });
});

describe("an app's logs", () => {
  it("say how long ago the box read them, or that it is still being asked", () => {
    expect(readAgo(100, 104.4)).toBe("read 4 s ago");
    expect(readAgo(null, 104)).toBe("asking the box for its lines…");
  });
});

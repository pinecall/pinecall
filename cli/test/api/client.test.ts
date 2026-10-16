/** The gateway client: signed requests, a query with its blanks left out, JSON or bytes, and every non-2xx a GatewayError in FastAPI's words. */

import { http, HttpResponse } from "msw/http";
import { describe, expect, it } from "vitest";

import { detailOf, GatewayClient, seg } from "../../src/api/client.js";
import { GatewayError } from "../../src/errors.js";
import { answer, GATEWAY, KEY, refuse, server } from "../support/gateway.js";

const gw = new GatewayClient(`${GATEWAY}/`, KEY, "production");

describe("a request", () => {
  it("is signed with the key and the env, its query's undefined values left out", async () => {
    const sent = answer("get", "/v1/things", { ok: true });
    expect(await gw.get("/v1/things", { a: 1, b: undefined, c: true })).toEqual({ ok: true });
    expect(sent[0]).toMatchObject({ authorization: `Bearer ${KEY}`, env: "production", query: { a: "1", c: "true" } });
  });

  it("sends JSON as JSON and bytes as they are", async () => {
    const sent = answer("post", "/v1/things", null);
    await gw.post("/v1/things", { a: 1 });
    await gw.request("/v1/things", { method: "POST", body: Buffer.from([1, 2, 3]), headers: { "content-type": "application/gzip" } });
    expect(sent.map((one) => [one.type, one.body])).toEqual([["application/json", { a: 1 }], ["application/gzip", 3]]);
  });

  it("an empty answer is null", async () => {
    answer("delete", "/v1/things", null);
    expect(await gw.delete("/v1/things")).toBeNull();
  });

  it("a refusal is a GatewayError with the status and the detail", async () => {
    refuse("get", "/v1/things", 409, "already going");
    await expect(gw.get("/v1/things")).rejects.toEqual(new GatewayError(409, "already going"));
  });

  it("a body that is no JSON is the detail as it came", async () => {
    server.use(http.get(`${GATEWAY}/v1/things`, () => new HttpResponse("upstream timeout", { status: 504 })));
    await expect(gw.get("/v1/things")).rejects.toMatchObject({ status: 504, detail: "upstream timeout" });
  });
});

describe("FastAPI's detail", () => {
  it("a 422's list is the fields and what is wrong with each", () => {
    expect(detailOf(JSON.stringify({ detail: [{ loc: ["body", "turns", 0], msg: "Field required" }, { loc: ["body"], msg: "bad" }] }))).toBe("turns.0: Field required; bad");
  });

  it("a string is itself, and anything else the text whole", () => {
    expect(detailOf(JSON.stringify({ detail: "no" }))).toBe("no");
    expect(detailOf('{"error":"x"}')).toBe('{"error":"x"}');
  });
});

describe("a path", () => {
  it("escapes a segment, and a URL keeps the base's own path", () => {
    expect(seg("+34 600/1")).toBe("%2B34%20600%2F1");
    expect(new GatewayClient("https://box.example.com/pinecall", KEY, "sandbox").urlOf("/v1/x", { a: "b" })).toBe("https://box.example.com/pinecall/v1/x?a=b");
  });
});

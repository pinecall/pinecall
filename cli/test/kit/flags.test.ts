/** A flag's text read into the value a service takes, and repeated key=value pairs. */

import { describe, expect, it } from "vitest";

import { listOf, numberOf } from "../../src/kit/flags.js";
import { parseKeyValues } from "../../src/kit/keyvalue.js";

describe("flags", () => {
  it("a number is one, or the flag is named", () => {
    expect(numberOf("--k", "4")).toBe(4);
    expect(numberOf("--k", undefined)).toBeUndefined();
    expect(() => numberOf("--k", "four")).toThrow("--k takes a number, not four");
    expect(() => numberOf("--k", " ")).toThrow();
  });

  it("a list is comma-separated, blanks dropped", () => {
    expect(listOf(" a, ,b ")).toEqual(["a", "b"]);
    expect(listOf(undefined)).toBeUndefined();
  });

  it("key=value pairs read each value as JSON when it parses", () => {
    expect(parseKeyValues("option", ["n=3", "on=true", "url=http://x:8000/v1", "list=[1,2]"])).toEqual({ n: 3, on: true, url: "http://x:8000/v1", list: [1, 2] });
    expect(() => parseKeyValues("option", ["=x"])).toThrow("--option =x is not key=value");
  });
});

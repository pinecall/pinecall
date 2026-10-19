/** A zip read whole: every file's path and bytes, stored or deflated; an archive that is none, or that climbs out of its folder, refused. */

import { describe, expect, it } from "vitest";

import { NOT_A_ZIP, unzip } from "../../src/kit/zip.js";
import { zipOf } from "../support/zip.js";

describe("an archive", () => {
  it("is read file by file, deflated or stored", () => {
    const files = { "clinica/package.json": '{"name":"clinica"}'.repeat(40), "clinica/README.md": "" };
    for (const stored of [false, true]) {
      expect(unzip(zipOf(files, stored)).map((entry) => [entry.path, entry.data.toString()])).toEqual(Object.entries(files));
    }
  });

  it("that is no zip is refused", () => {
    expect(() => unzip(Buffer.from("not a zip at all, only words"))).toThrow(NOT_A_ZIP);
    expect(() => unzip(new Uint8Array(0))).toThrow(NOT_A_ZIP);
  });

  it("naming a path outside its folder is refused", () => {
    expect(() => unzip(zipOf({ "../outside.txt": "x" }))).toThrow(/outside the folder/);
    expect(() => unzip(zipOf({ "/etc/passwd": "x" }))).toThrow(/outside the folder/);
  });
});

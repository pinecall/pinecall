/** Goldens on disk: one or several a file, named by the file when unnamed, sorted, filtered; the other goldens beside them skipped. */

import { describe, expect, it } from "vitest";

import { goldensIn, goldensInFolder, matching } from "../../../src/evals/service/goldens.js";
import { folder, write } from "../../support/project.js";

describe("goldens", () => {
  it("are read one level deep, sorted by file, named by the file when unnamed", async () => {
    const dir = folder();
    write(dir, "b-books.json", JSON.stringify({ turns: [{ say: "Thursday?" }] }));
    write(dir, "a-asks.json", JSON.stringify([{ turns: [{ say: "Hi" }] }, { name: "spelled", turns: [{ say: "Ana" }] }]));
    write(dir, "docs.json", "[]");
    write(dir, "memory.json", "[]");
    write(dir, "notes.txt", "not a golden");
    expect((await goldensIn([dir])).map((one) => one.name)).toEqual(["a-asks #1", "spelled", "b-books"]);
  });

  it("a folder that is not there holds none", async () => {
    expect(await goldensInFolder("/nowhere/at/all")).toEqual([]);
  });

  it("a file named is read as itself", async () => {
    const file = write(folder(), "one.json", JSON.stringify({ turns: [] }));
    expect((await goldensIn([file])).map((one) => one.name)).toEqual(["one"]);
  });

  it("are kept by a part of their name, any case", () => {
    expect(matching([{ name: "Books Thursday" }, { name: "asks" }], "THURS")).toEqual([{ name: "Books Thursday" }]);
  });
});

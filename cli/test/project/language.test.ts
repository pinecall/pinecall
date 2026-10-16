/** Which language an agent is in, and the command that serves it: the project's own interpreter and framework. */

import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { languageOf, serveCommand } from "../../src/project/language.js";
import { folder, write } from "../support/project.js";

describe("the language", () => {
  it("is the file's", () => {
    expect(["agent.tsx", "agent.ts", "agent.rb", "agent.py"].map(languageOf)).toEqual(["typescript", "typescript", "ruby", "python"]);
  });

  it("Ruby runs through bundler when the project has a Gemfile, and no debugger attaches to it", () => {
    const root = folder();
    expect(serveCommand("ruby", "start", ["--file", "a.rb"], { root })).toEqual(["ruby", "-r", "pinecall", "-e", "exit Pinecall::Serve.main(ARGV)", "--", "start", "--file", "a.rb"]);
    write(root, "Gemfile", "");
    expect(serveCommand("ruby", "prompt", [], { root })[0]).toBe("bundle");
    expect(() => serveCommand("ruby", "start", [], { root, inspect: ["--inspect"] })).toThrow(/a Ruby agent runs no Node/);
  });

  it("Python runs on the project's .venv when it has one", () => {
    const root = folder();
    expect(serveCommand("python", "start", [], { root })[0]).toBe("python3");
    write(root, ".venv/bin/python", "");
    expect(serveCommand("python", "start", [], { root })).toEqual([join(root, ".venv/bin/python"), "-m", "pinecall.serve", "start"]);
  });

  it("TypeScript is served by the project's own framework, and refused when it installed none", () => {
    expect(() => serveCommand("typescript", "start", [], { root: folder() })).toThrow(/npm i @pinecall\/agents/);
    expect(serveCommand("typescript", "start", ["--events"], { root: folder(), serve: "/lent/serve.js", inspect: ["--inspect=9230"] })).toEqual([process.execPath, "--inspect=9230", "/lent/serve.js", "start", "--events"]);
  });
});

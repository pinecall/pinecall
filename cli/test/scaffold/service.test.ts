/** Scaffold on disk: a project written from its language's templates, an agent's folder in it, a golden never written over. */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import * as service from "../../src/scaffold/service.js";
import { folder, project, write } from "../support/project.js";

const VERSION = (JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8")) as { version: string }).version;

describe("a new project", () => {
  it("is the project alone: its toolchain under its own name, an empty agents/, the framework at this CLI's version", () => {
    const root = join(folder(), "clinica-dental");
    expect(service.createProject(root, "clinica-dental", "typescript")).toEqual({ root, template: "typescript", agent: undefined });
    for (const file of [".gitignore", "README.md", "package.json", "tsconfig.json", "vitest.config.ts"]) expect(existsSync(join(root, file)), file).toBe(true);
    expect(readdirSync(join(root, "agents"))).toEqual([]);
    const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as { name: string; dependencies: Record<string, string> };
    expect(manifest.name).toBe("clinica-dental");
    expect(manifest.dependencies["@pinecall/agents"]).toBe(`^${VERSION}`);
    expect(readFileSync(join(root, "README.md"), "utf8")).toContain("# Clinica Dental");
  });

  it("with --agent holds its first agent, whose folder holds its class, its test and its golden", () => {
    const root = join(folder(), "clinica-dental");
    expect(service.createProject(root, "clinica-dental", "typescript", "sofia").agent).toBe("sofia");
    for (const file of ["agents/sofia/agent.tsx", "agents/sofia/test/agent.test.ts", "agents/sofia/test/goldens/takes-the-message.json", "agents/sofia/judges/README.md", "agents/sofia/test/personas/hurried.json"]) {
      expect(existsSync(join(root, file)), file).toBe(true);
    }
    expect(readFileSync(join(root, "agents/sofia/agent.tsx"), "utf8")).toContain("static judges = judges({ on: RECOMMENDED })");
    expect(readFileSync(join(root, "agents/sofia/judges/README.md"), "utf8")).toContain("in agent.tsx");
    expect(readFileSync(join(root, "agents/sofia/agent.tsx"), "utf8")).not.toMatch(/\{\{\w+\}\}/);
    expect(readFileSync(join(root, "agents/sofia/test/agent.test.ts"), "utf8")).toContain('import Sofia from "../agent.js";');
  });

  it("is written in Ruby and in Python from their own templates, each test beside its class", () => {
    const ruby = join(folder(), "clinica");
    service.createProject(ruby, "clinica", "ruby", "sales");
    for (const file of ["agents/sales/agent.rb", "agents/sales/views/sales.erb", "agents/sales/test/agent_test.rb", "agents/sales/judges/README.md", "agents/sales/test/personas/hurried.json", "Rakefile"]) expect(existsSync(join(ruby, file)), file).toBe(true);
    expect(readFileSync(join(ruby, "agents/sales/agent.rb"), "utf8")).toContain("judges on: %w[consent");
    expect(readFileSync(join(ruby, "Rakefile"), "utf8")).toContain('FileList["agents/*/test/**/*_test.rb"]');
    const python = join(folder(), "clinica");
    service.createProject(python, "clinica", "python", "sales");
    for (const file of ["agents/sales/agent.py", "agents/sales/test/test_agent.py", "agents/sales/judges/README.md", "agents/sales/test/personas/hurried.json"]) expect(existsSync(join(python, file)), file).toBe(true);
    expect(readFileSync(join(python, "agents/sales/agent.py"), "utf8")).toContain("judges = judges(on=RECOMMENDED)");
    expect(readFileSync(join(python, "pyproject.toml"), "utf8")).toContain('name = "clinica"');
  });

  it("is refused for a name the gateway would not take, or a folder already in use", () => {
    expect(() => service.createProject(join(folder(), "x"), "Front_Desk", "typescript")).toThrow("cannot be a project's name");
    expect(() => service.createProject(join(folder(), "x"), "clinica", "typescript", "Sofia")).toThrow("cannot be an agent's name");
    const used = project();
    expect(() => service.createProject(used, "front-desk", "typescript")).toThrow(/already holds files/);
  });

  it("takes one language", () => {
    expect(service.templateOf({})).toBeUndefined();
    expect(service.templateOf({ ruby: true })).toBe("ruby");
    expect(() => service.templateOf({ ruby: true, python: true })).toThrow("--ruby or --python, not both: one language");
  });

  it("names the class and the title from the slug", () => {
    expect(service.wordsFor("front-desk", "ruby")).toMatchObject({ slug: "front-desk", Class: "FrontDesk", Title: "Front Desk", install: "bundle install" });
  });
});

describe("one more agent", () => {
  it("is one folder in the project's language, its files answered relative to the root", () => {
    const root = project(["front-desk"]);
    const files = service.createAgent(root, "sales");
    expect(files).toContain(join("agents", "sales", "agent.tsx"));
    expect(files).toContain(join("agents", "sales", "test", "goldens", "takes-the-message.json"));
    expect(files.every((file) => file.startsWith(join("agents", "sales")))).toBe(true);
  });

  it("is refused outside a project, for an agent already there, and for a project of two languages", () => {
    expect(() => service.createAgent(folder(), "sales")).toThrow(/no project at/);
    expect(() => service.createAgent(project(["front-desk"]), "front-desk")).toThrow(/is an agent of this project already/);
    const mixed = project(["front-desk"]);
    write(mixed, "agents/sales/agent.rb", "class Sales; end\n");
    expect(() => service.createAgent(mixed, "billing")).toThrow(/say which with --typescript, --ruby or --python/);
  });
});

describe("a golden", () => {
  it("is a turn per line said, the tools in its expect, under the agent's goldens", () => {
    const root = project(["front-desk"]);
    const file = service.createGolden(root, service.GoldenInput.parse({ name: "asks-for-a-refund", says: ["Hi, I want a refund.", "  ", "It's Ana Ruiz."], tools: ["takeMessage"] }));
    expect(file).toBe(join(root, "agents/front-desk/test/goldens/asks-for-a-refund.json"));
    expect(JSON.parse(readFileSync(file, "utf8"))).toEqual({ turns: [{ say: "Hi, I want a refund." }, { say: "It's Ana Ruiz." }], expect: { tools: ["takeMessage"] } });
  });

  it("is never written over", () => {
    const root = project(["front-desk"], { "agents/front-desk/test/goldens/books.json": "{}" });
    expect(() => service.createGolden(root, service.GoldenInput.parse({ name: "books", says: ["Hi"] }))).toThrow(/a golden is never written over/);
  });

  it("needs a line, a name that is a file's, and the agent when the project holds two", () => {
    expect(() => service.GoldenInput.parse({ name: "x", says: [" "] })).toThrow(/a golden needs what the caller says/);
    expect(() => service.GoldenInput.parse({ name: "Books Thursday", says: ["Hi"] })).toThrow(/a golden's name/);
    const two = project(["front-desk", "sales"]);
    expect(() => service.createGolden(two, service.GoldenInput.parse({ name: "x", says: ["Hi"] }))).toThrow("this project has 2 agents: name one with --agent front-desk or --agent sales");
  });
});

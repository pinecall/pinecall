// A tool that stops to ask: its call answered with the question, its function going on when the answer is given.

import { describe, expect, it } from "vitest";

import { GetEmail, GetPhone, givingTool } from "../../src/agent/tasks.js";
import { DeclarationRefused } from "../../src/agent/tools.js";
import { Asking, givingTools } from "../../src/runtime/asking.js";
import { ToolFailed } from "../../src/runtime/run-tool.js";

describe("a tool that asks", () => {
  it("is answered with the question, and the tool that gives the answer with what the first returned", async () => {
    const asking = new Asking([GetEmail]);
    const book = async (): Promise<string> => `booked for ${await asking.ask(GetEmail)}`;

    expect(await asking.run("book", book)).toMatch(/it needs the caller's email address.*Then call give_email\.$/);
    expect(asking.open).toEqual(givingTool(GetEmail));

    expect(await asking.given("give_email", { email: "Ana@Example.com" })).toEqual({ finished: "book", result: "booked for ana@example.com" });
    expect(asking.open).toBeUndefined();
  });

  it("asks twice in one tool: the first answer is answered with the second question", async () => {
    const asking = new Asking([GetEmail, GetPhone]);
    const book = async (): Promise<string[]> => [await asking.ask(GetEmail), await asking.ask(GetPhone)];

    await asking.run("book", book);
    expect(await asking.given("give_email", { email: "ana@example.com" })).toMatch(/a phone number to reach the caller at/);
    expect(asking.open?.name).toBe("give_phone");
    expect(await asking.given("give_phone", { number: "+1 415 555 0142" })).toEqual({ finished: "book", result: ["ana@example.com", "+14155550142"] });
  });

  it("keeps asking when the answer does not pass the task's check", async () => {
    const asking = new Asking([GetEmail]);
    await asking.run("book", async () => asking.ask(GetEmail));

    await expect(asking.given("give_email", { email: "ana at example" })).rejects.toThrow(ToolFailed);
    await expect(asking.given("give_email", {})).rejects.toThrow(/email must be given/);
    expect(asking.open?.name).toBe("give_email");
    expect(await asking.given("give_email", { email: "ana@example.com" })).toEqual({ finished: "book", result: "ana@example.com" });
  });

  it("answers a tool that asks nothing with what it returned, and one that throws with what it threw", async () => {
    const asking = new Asking([GetEmail]);
    expect(await asking.run("book", async () => "done")).toBe("done");
    await expect(asking.run("book", async () => Promise.reject(new ToolFailed("no such slot")))).rejects.toThrow("no such slot");
  });

  it("fails the tool whose function throws after the answer", async () => {
    const asking = new Asking([GetEmail]);
    await asking.run("book", async () => {
      await asking.ask(GetEmail);
      throw new ToolFailed("that time was just taken");
    });
    await expect(asking.given("give_email", { email: "ana@example.com" })).rejects.toThrow("that time was just taken");
  });
});

describe("what is refused", () => {
  it("is an ask outside a tool, of a task the class did not declare, or while another is open", async () => {
    const asking = new Asking([GetEmail]);
    await expect(asking.ask(GetEmail)).rejects.toThrow(/ask is for inside a tool/);
    await expect(asking.run("book", async () => asking.ask(GetPhone))).rejects.toThrow(/phone is not a task of this agent/);

    await asking.run("book", async () => asking.ask(GetEmail));
    await expect(asking.run("book", async () => asking.ask(GetEmail))).rejects.toThrow(/email is being asked for: one question at a time/);
  });

  it("is an answer nobody asked for", async () => {
    const asking = new Asking([GetEmail]);
    expect(asking.gives("give_email")).toBe(true);
    expect(asking.gives("book")).toBe(false);
    await expect(asking.given("give_email", { email: "ana@example.com" })).rejects.toThrow(/nothing is being asked for/);
  });

  it("is a task whose tool an agent already declares", () => {
    expect(givingTools([GetEmail], ["book"]).map((spec) => spec.name)).toEqual(["give_email"]);
    expect(() => givingTools([GetEmail], ["give_email"])).toThrow(DeclarationRefused);
  });
});

describe("a call that ends with a question open", () => {
  it("tells the tool that asked", async () => {
    const asking = new Asking([GetEmail]);
    let thrown: Error | undefined;
    await asking.run("book", async () => {
      try {
        await asking.ask(GetEmail);
      } catch (ended) {
        thrown = ended as Error;
      }
    });

    asking.abandon();
    await new Promise((resolve) => setImmediate(resolve));

    expect(thrown?.message).toBe("the call ended before the caller gave the caller's email address");
    expect(asking.open).toBeUndefined();
  });
});

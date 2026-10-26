// What the visitor typed is sent with the page, and the dot does the one thing decided: a walk, a thing shown, or the agent offered.

import { afterEach, describe, expect, it } from "vitest";

import { Page } from "../../src/page/page.js";
import { act, askWords, type Asked } from "../../src/tutor/ask.js";

afterEach(() => {
  document.body.innerHTML = "";
});

function anAsked(answer: unknown | Error): { on: Asked; done: string[]; sent: unknown[] } {
  document.body.innerHTML = `<main><section aria-label="Pricing"><h2>Pricing</h2></section><section aria-label="Compare the plans"><h2>Compare</h2></section></main>`;
  const done: string[] = [];
  const sent: unknown[] = [];
  const on: Asked = {
    ask: async (request) => {
      sent.push(request);
      if (answer instanceof Error) throw answer;
      return answer;
    },
    page: new Page(document),
    path: () => "/pricing",
    walks: () => [{ name: "plans", title: "Which plan is yours" }],
    play: (walk, values) => void done.push(`play ${walk}${Object.keys(values).length > 0 ? ` ${JSON.stringify(values)}` : ""}`),
    unlock: () => void done.push("unlock"),
    show: (element, role, name) => void done.push(`show ${role} ${name} ${element.tagName.toLowerCase()}`),
    note: (text) => void done.push(`note ${text ?? "-"}`),
    offer: (text, action) => {
      done.push(`offer ${text}${action ? ` [${action.label}]` : ""}`);
      action?.onClick();
    },
    talk: (message) => void done.push(`talk ${message}`),
    words: askWords(),
  };
  return { on, done, sent };
}

describe("what the visitor typed", () => {
  it("is sent with the page's path, its things and its walks, while the face says it is looking", async () => {
    const { on, done, sent } = anAsked({ do: "walk", walk: "plans", confidence: 0.9 });

    await act("show me the plans", on);

    expect(sent[0]).toMatchObject({ decide: { message: "show me the plans", path: "/pricing", walks: [{ name: "plans" }] } });
    expect((sent[0] as { decide: { page: string } }).decide.page).toContain('region "Compare the plans"');
    // The audio is let play inside the submit: the walk starts after the door answers.
    expect(done).toEqual(["unlock", "note Looking…", "note -", "play plans"]);
  });

  it("plays a walk with the values picked out of what was typed", async () => {
    const { on, done } = anAsked({ do: "walk", walk: "plans", params: { name: "Jordan Lee" }, confidence: 0.9 });

    await act("book it for Jordan Lee", on);

    expect(done.at(-1)).toBe('play plans {"name":"Jordan Lee"}');
  });

  it("shows the thing decided, by the ref the page gave it, with its role and name", async () => {
    const { on, done } = anAsked(null);
    // A ref is stable for the page's life: the one the page gave is the one the decision names.
    const ref = /region "Compare the plans" \[ref=(e\d+)\]/.exec(on.page.seen().text)?.[1];
    on.ask = async () => ({ do: "show", target: ref, confidence: 0.9 });

    await act("where do I compare them?", on);

    expect(done.at(-1)).toBe("show region Compare the plans section");
  });

  it("offers the agent for a question a person answers, and says it cannot find what is not here or not answered", async () => {
    const talking = anAsked({ do: "talk", confidence: 0.8 });
    await act("can I get a discount?", talking.on);
    expect(talking.done.slice(-2)).toEqual(["offer That one is a question for the agent. [Ask the agent]", "talk can I get a discount?"]);

    const strange = anAsked({ do: "show", target: "e999", confidence: 0.9 });
    await act("show me the moon", strange.on);
    expect(strange.done.at(-2)).toBe("offer I can't find that on this page. [Ask the agent]");

    const down = anAsked(new Error("offline"));
    await act("anything", down.on);
    expect(down.done).toContain("offer I can't find that on this page. [Ask the agent]");
  });
});

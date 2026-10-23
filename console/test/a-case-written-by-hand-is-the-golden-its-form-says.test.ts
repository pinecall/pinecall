/** New case: the form's lines, state and checks are the golden the gateway keeps, and what it cannot be is said. */

import { expect, test } from "vitest";

import { BLANK, goldenOf } from "../src/screens/cases/written";

test("one line a line, phrases and tools by comma, and nothing sent that was left empty", () => {
  const made = goldenOf({
    ...BLANK,
    name: " no-dice-un-precio ",
    lines: "¿Cuánto cuesta una resonancia?\n\n  ¿Y con seguro?  ",
    not: "euros, €,",
    tools: "find_slot",
    grounded: true,
    register: "usted",
  });
  expect(made).toEqual({
    golden: {
      name: "no-dice-un-precio",
      turns: [{ say: "¿Cuánto cuesta una resonancia?" }, { say: "¿Y con seguro?" }],
      expect: { not: ["euros", "€"], tools: ["find_slot"], grounded: true, register: "usted" },
    },
  });
});

test("a class's state rides the golden, and a case that checks nothing yet is still a case", () => {
  expect(goldenOf({ ...BLANK, name: "abre-en-book", lines: "Sí, esa", state: '{"stage": "book"}' })).toEqual({
    golden: { name: "abre-en-book", state: { stage: "book" }, turns: [{ say: "Sí, esa" }] },
  });
});

test("no name, no line, a state that is not a JSON object: each is refused by what is missing", () => {
  expect(goldenOf({ ...BLANK, lines: "Hola" })).toEqual({ refused: "Name the case." });
  expect(goldenOf({ ...BLANK, name: "x", lines: " \n " })).toEqual({ refused: "Write at least one line the caller says." });
  expect(goldenOf({ ...BLANK, name: "x", lines: "Hola", state: "{stage" })).toEqual({ refused: "The state is not JSON." });
  expect(goldenOf({ ...BLANK, name: "x", lines: "Hola", state: "[1]" })).toMatchObject({ refused: expect.stringContaining("JSON object") });
});

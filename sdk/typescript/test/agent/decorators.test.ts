// The class decorators: what `@tool` is refused on, and in whose words.

import { expect, it } from "vitest";

import { Agent, DeclarationRefused, tool } from "../../src/index.js";

it("refuses @tool on a field with the sentence the docs promise, not a TypeError from inside the decorator", () => {
  expect(() => {
    class OnAField extends Agent {
      // @ts-expect-error a field is no place for @tool, and the compiler says so as well
      @tool() book = 1;
    }
    return OnAField;
  }).toThrow(new DeclarationRefused("@tool goes on a method; book is not one"));
});

/** The guide's tokenizer: a comment, a string, a decorator, a keyword and a type each get their own class, and the rest stays as it is. */

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { highlighted } from "../src/screens/welcome/highlight";

const html = (code: string, language: "typescript" | "ruby" | "python"): string => renderToStaticMarkup(<>{highlighted(code, language)}</>);

describe("the guide's code", () => {
  it("colours TypeScript by kind", () => {
    const out = html('/** who */\n@tool()\nexport class FrontDesk extends Agent { x = "s"; }', "typescript");
    expect(out).toContain('<span class="wel-tok-comment">/** who */</span>');
    expect(out).toContain('<span class="wel-tok-decorator">@tool</span>');
    expect(out).toContain('<span class="wel-tok-keyword">class</span>');
    expect(out).toContain('<span class="wel-tok-type">FrontDesk</span>');
    expect(out).toContain('<span class="wel-tok-string">&quot;s&quot;</span>');
  });
  it("keeps a Ruby symbol as a string and a comment whole", () => {
    const out = html("# the prompt\nstage :ask", "ruby");
    expect(out).toContain('<span class="wel-tok-comment"># the prompt</span>');
    expect(out).toContain('<span class="wel-tok-string">:ask</span>');
  });
  it("takes a Python docstring as one comment", () => {
    expect(html('"""two\nlines"""\ndef f(): None', "python")).toContain('<span class="wel-tok-comment">&quot;&quot;&quot;two\nlines&quot;&quot;&quot;</span>');
  });
});

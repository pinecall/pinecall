/** The org's email layout from the CLI: a file that says where the reply goes, kept; words tried on it; cleared. */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { UsageError } from "../../src/errors.js";
import * as render from "../../src/email/render.js";
import * as service from "../../src/email/service.js";
import { answer } from "../support/gateway.js";
import { testContext } from "../support/context.js";
import { folder } from "../support/project.js";

const OURS = "<html><body><h1>Acme</h1>{{content}}</body></html>";

describe("email layout", () => {
  it("keeps a file that says once where the reply goes, and refuses one that says it nowhere or twice", async () => {
    const dir = folder();
    const kept = join(dir, "acme.html");
    writeFileSync(kept, OURS);
    const sent = answer("put", "/v1/org/email/layout", { html: OURS, own: true });
    const { ctx } = testContext();
    expect(await service.setLayout(ctx, kept)).toEqual({ html: OURS, own: true });
    expect(sent[0]!.body).toEqual({ html: OURS });
    for (const [name, html] of [["nowhere.html", "<p>no place</p>"], ["twice.html", "{{content}}{{content}}"]] as const) {
      writeFileSync(join(dir, name), html);
      await expect(service.setLayout(ctx, join(dir, name))).rejects.toBeInstanceOf(UsageError);
    }
    await expect(service.setLayout(ctx, join(dir, "missing.html"))).rejects.toThrow(/no file/);
  });

  it("tries words on a layout before it is kept, and writes the HTML where it is told", async () => {
    const dir = folder();
    writeFileSync(join(dir, "try.html"), OURS);
    const sent = answer("post", "/v1/org/email/layout/preview", { subject: "Re: Horarios", html: "<h1>Acme</h1><p>Hola</p>", text: "Hola" });
    const { ctx } = testContext();
    const out = join(dir, "reply.html");
    const shown = await service.previewLayout(ctx, service.PreviewInput.parse({ text: "Hola", subject: "Horarios", file: join(dir, "try.html"), out }));
    expect(sent[0]!.body).toEqual({ text: "Hola", subject: "Horarios", html: OURS });
    expect([shown.subject, shown.written, readFileSync(out, "utf8")]).toEqual(["Re: Horarios", out, "<h1>Acme</h1><p>Hola</p>"]);
  });

  it("with no template sends text alone: kept without HTML, shown as that, and a preview has no HTML to write", async () => {
    const kept = { html: "<p>{{content}}</p>", own: true, text_only: true };
    const sent = answer("put", "/v1/org/email/layout", kept);
    const asked = answer("post", "/v1/org/email/layout/preview", { subject: "Re: Horarios", html: null, text: "Hola Ana" });
    const { ctx } = testContext();
    expect(await service.sendTextOnly(ctx)).toEqual(kept);
    expect(sent[0]!.body).toEqual({ text_only: true });
    expect(render.layout(kept)[0]).toBe("text alone: no template, and no HTML part in the org's emails");
    const out = join(folder(), "reply.html");
    const shown = await service.previewLayout(ctx, service.PreviewInput.parse({ text: "Hola **Ana**", textOnly: true, out }));
    expect(asked[0]!.body).toEqual({ text: "Hola **Ana**", text_only: true });
    expect([shown.html, shown.written, existsSync(out)]).toEqual([null, null, false]);
    expect(render.preview(shown).at(-1)).toBe("text alone: this is the whole email, with no HTML part");
  });
});

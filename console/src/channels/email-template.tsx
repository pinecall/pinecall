/** The org's email template: made from a brand, a colour, a logo and a footer, or written as HTML; tried on a reply before it is kept. */

import { useEffect, useState, type ReactNode } from "react";

import { drop, post, put, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Field } from "../ui/setting";
import "../calls/email.css";

const DOOR = "/v1/org/email/layout";
const SAMPLE = "Hola Ana,\n\nGracias por escribirnos. Te confirmo los horarios:\n\n- **Sábado** de 10 a 14\n- Domingo cerrado\n\nPodés reservar en [nuestra web](https://example.com).\n\nUn saludo,\nEl equipo";

interface Simple {
  brand: string;
  accent: string;
  logo: string;
  footer: string;
}

const PLAINLY: Simple = { brand: "", accent: "#5b3df5", logo: "", footer: "" };
// The choices the simple template was made from, kept in it, so it opens again as it was made.
const MARK = /<!-- pinecall-template (\{.*?\}) -->/;

const escaped = (text: string): string => text.replace(/[&<>"]/g, (one) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[one] ?? one);

/** A template from the four choices: a white card on a soft ground, the brand above, the reply, the footer below. */
export function templateOf(made: Simple): string {
  const accent = /^#[0-9a-fA-F]{6}$/.test(made.accent) ? made.accent : PLAINLY.accent;
  const font = "Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif";
  const logo = made.logo.trim() === "" ? "" : `<img src="${escaped(made.logo.trim())}" alt="" height="28" style="height:28px;vertical-align:middle;margin-right:10px;border:0;">`;
  const brand = made.brand.trim() === "" && logo === "" ? "" : `<tr><td style="padding:20px 28px;border-bottom:1px solid #efedf5;font-family:${font};">${logo}<span style="font-size:17px;font-weight:700;color:${accent};">${escaped(made.brand.trim())}</span></td></tr>`;
  const footer = made.footer.trim() === "" ? "" : `<tr><td style="padding:12px 28px 22px;font-family:${font};font-size:12px;line-height:1.5;color:#8a879a;">${escaped(made.footer.trim())}</td></tr>`;
  return [
    `<!doctype html><!-- pinecall-template ${JSON.stringify(made)} -->`,
    `<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>a{color:${accent};}</style></head>`,
    `<body style="margin:0;padding:0;background:#f6f5fb;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f5fb;padding:28px 12px;"><tr><td align="center">`,
    `<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;border:1px solid #ebe9f3;">`,
    brand,
    `<tr><td style="padding:24px 28px 10px;font-family:${font};font-size:15px;line-height:1.6;color:#1d1b26;">{{content}}</td></tr>`,
    footer,
    `</table></td></tr></table></body></html>`,
  ].join("\n");
}

function simpleOf(html: string): Simple | null {
  const found = MARK.exec(html);
  if (found === null) return null;
  try {
    return { ...PLAINLY, ...(JSON.parse(found[1] ?? "{}") as Partial<Simple>) };
  } catch {
    return null;
  }
}

export function EmailTemplate(): ReactNode {
  const credentials = useCredentials();
  const [own, setOwn] = useState(false);
  const [mode, setMode] = useState<"simple" | "html">("simple");
  const [simple, setSimple] = useState<Simple>(PLAINLY);
  const [html, setHtml] = useState("");
  const [sample, setSample] = useState(SAMPLE);
  const [preview, setPreview] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const written = mode === "simple" ? templateOf(simple) : html;

  useEffect(() => {
    void read(credentials, DOOR).then((answer) => {
      const kept = String(Reflect.get(Object(answer), "html") ?? "");
      const isOwn = Reflect.get(Object(answer), "own") === true;
      setOwn(isOwn);
      setHtml(kept);
      const made = isOwn ? simpleOf(kept) : PLAINLY;
      if (made !== null) setSimple(made);
      setMode(made === null ? "html" : "simple");
    });
  }, [credentials]);

  // The preview follows the typing, a moment after it stops: the gateway sets the sample in the template as a reply.
  useEffect(() => {
    if (!written.includes("{{content}}") || sample.trim() === "") return;
    const later = setTimeout(() => {
      void post(credentials, `${DOOR}/preview`, { text: sample, subject: "Horarios", html: written })
        .then((answer) => setPreview(String(Reflect.get(Object(answer), "html") ?? "")))
        .catch(() => setPreview(""));
    }, 400);
    return () => clearTimeout(later);
  }, [credentials, written, sample]);

  const keep = async (): Promise<void> => {
    setBusy(true);
    try {
      await put(credentials, DOOR, { html: written });
      setOwn(true);
      setSaid("Kept: the agents' next emails are set in it.");
    } catch (failed) {
      setSaid(failed instanceof Error ? failed.message : "The template was not kept.");
    } finally {
      setBusy(false);
    }
  };
  const forget = async (): Promise<void> => {
    setBusy(true);
    try {
      await drop(credentials, DOOR);
      setOwn(false);
      setSimple(PLAINLY);
      setMode("simple");
      setSaid("Back to the plain template.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="dash-card mail-template" aria-label="Email template">
      <header className="mail-template-head">
        <span className="dash-eyebrow">Email template</span>
        <span className="dash-quiet">{own ? "The org's own, for every agent's emails." : "The plain one: white, nobody's brand. Make it yours."}</span>
        <div className="dash-switch" role="group" aria-label="How the template is made">
          <button type="button" className={mode === "simple" ? "dash-switch-on" : ""} aria-pressed={mode === "simple"} onClick={() => setMode("simple")}>
            Simple
          </button>
          <button type="button" className={mode === "html" ? "dash-switch-on" : ""} aria-pressed={mode === "html"} onClick={() => (setHtml(written), setMode("html"))}>
            HTML
          </button>
        </div>
      </header>
      <div className="mail-template-body">
        <div className="mail-template-form">
          {mode === "simple" ? (
            <>
              <Field label="Brand">
                <input className="cfg-input" aria-label="Brand" placeholder="Your Company" value={simple.brand} onChange={(event) => setSimple({ ...simple, brand: event.target.value })} />
              </Field>
              <Field label="Colour">
                <span className="mail-colour">
                  <input type="color" aria-label="Colour" value={simple.accent} onChange={(event) => setSimple({ ...simple, accent: event.target.value })} />
                  <span className="dash-quiet">{simple.accent}</span>
                </span>
              </Field>
              <Field label="Logo">
                <input className="cfg-input" aria-label="Logo" placeholder="Optional: https://yourcompany.com/logo.png" value={simple.logo} onChange={(event) => setSimple({ ...simple, logo: event.target.value })} />
              </Field>
              <Field label="Footer">
                <textarea className="cfg-input cfg-area" rows={2} aria-label="Footer" placeholder="Optional: Your Company · Calle 1, Madrid · Reply to this email to reach us" value={simple.footer} onChange={(event) => setSimple({ ...simple, footer: event.target.value })} />
              </Field>
            </>
          ) : (
            <Field label="HTML">
              <textarea className="cfg-input cfg-area mail-code" rows={14} spellCheck={false} aria-label="HTML" value={html} onChange={(event) => setHtml(event.target.value)} />
              <span className="num-hint">{"{{content}}"} once, where the reply goes; {"{{subject}}"} wherever the subject shows.</span>
            </Field>
          )}
          <Field label="Try it on">
            <textarea className="cfg-input cfg-area" rows={5} aria-label="A reply to try" value={sample} onChange={(event) => setSample(event.target.value)} />
          </Field>
          <div className="cfg-dialog-foot mail-template-foot">
            {said !== null && <span className="dash-quiet">{said}</span>}
            {own && (
              <button type="button" className="app-button" disabled={busy} onClick={() => void forget()}>
                Use the plain one
              </button>
            )}
            <button type="button" className="cfg-save" disabled={busy || !written.includes("{{content}}")} onClick={() => void keep()}>
              {busy ? "Saving…" : "Save the template"}
            </button>
          </div>
        </div>
        <iframe className="mail-frame mail-template-preview" title="The reply as a contact would read it" sandbox="" srcDoc={preview} />
      </div>
    </section>
  );
}

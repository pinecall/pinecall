/** How the org's emails are set: with no template (text alone, or simple HTML), or in a template made from a brand, a colour, a logo and a footer, or written as HTML; tried on a reply before it is kept. */

import { useEffect, useState, type ReactNode } from "react";

import { drop, post, put, read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { Field } from "../ui/setting";
import "../calls/email.css";

const DOOR = "/v1/org/email/layout";
const SAMPLE = "Hola Ana,\n\nGracias por escribirnos. Te confirmo los horarios:\n\n- **Sábado** de 10 a 14\n- Domingo cerrado\n\nPodés reservar en [nuestra web](https://example.com).\n\nUn saludo,\nEl equipo";

/** `text`: one text part and no HTML. `none`: no template, the words as simple HTML. `simple` and `html`: a template. */
type Mode = "text" | "none" | "simple" | "html";
const MODES: readonly { mode: Mode; name: string; says: string }[] = [
  { mode: "text", name: "Text only", says: "No template and no HTML: the email is its words, as plain text. Links are written out." },
  { mode: "none", name: "No template", says: "No brand: the words as simple HTML on white, with their bold, lists, links and images." },
  { mode: "simple", name: "Simple", says: "A template made from your brand, a colour, a logo and a footer. No HTML to write." },
  { mode: "html", name: "HTML", says: "A template you write: {{content}} once, where the reply goes; {{subject}} wherever the subject shows." },
];

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
  const [kept, setKept] = useState<Mode>("none");
  const [mode, setMode] = useState<Mode>("none");
  const [simple, setSimple] = useState<Simple>(PLAINLY);
  const [html, setHtml] = useState("");
  const [sample, setSample] = useState(SAMPLE);
  const [preview, setPreview] = useState<{ html: string | null; text: string }>({ html: "", text: "" });
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const written = mode === "simple" ? templateOf(simple) : html;
  const templated = mode === "simple" || mode === "html";
  const ready = !templated || written.includes("{{content}}");

  useEffect(() => {
    void read(credentials, DOOR).then((answer) => {
      const page = String(Reflect.get(Object(answer), "html") ?? "");
      const isOwn = Reflect.get(Object(answer), "own") === true;
      const made = isOwn ? simpleOf(page) : null;
      const now: Mode = Reflect.get(Object(answer), "text_only") === true ? "text" : !isOwn ? "none" : made === null ? "html" : "simple";
      if (now === "html") setHtml(page);
      if (made !== null) setSimple(made);
      setKept(now);
      setMode(now);
    });
  }, [credentials]);

  // The preview follows the typing, a moment after it stops: the gateway sets the sample in the template as a reply.
  useEffect(() => {
    if (!ready || sample.trim() === "") return;
    const how = mode === "text" ? { text_only: true } : mode === "none" ? { plain: true, text_only: false } : { html: written, text_only: false };
    const later = setTimeout(() => {
      void post(credentials, `${DOOR}/preview`, { text: sample, subject: "Horarios", ...how })
        .then((answer) => {
          const page: unknown = Reflect.get(Object(answer), "html");
          setPreview({ html: typeof page === "string" ? page : null, text: String(Reflect.get(Object(answer), "text") ?? "") });
        })
        .catch(() => setPreview({ html: "", text: "" }));
    }, 400);
    return () => clearTimeout(later);
  }, [credentials, written, sample, mode, ready]);

  const keep = async (): Promise<void> => {
    setBusy(true);
    try {
      if (mode === "text") await put(credentials, DOOR, { text_only: true });
      else if (mode === "none") await drop(credentials, DOOR).catch(() => undefined);
      else await put(credentials, DOOR, { html: written });
      setKept(mode);
      setSaid(mode === "text" ? "Saved: the agents' next emails go as text alone." : mode === "none" ? "Saved: no template, the words as simple HTML." : "Saved: the agents' next emails are set in it.");
    } catch (failed) {
      setSaid(failed instanceof Error ? failed.message : "It was not saved.");
    } finally {
      setBusy(false);
    }
  };
  const chosen = MODES.find((one) => one.mode === mode);

  return (
    <section className="dash-card mail-template" aria-label="How the org's emails look">
      <header className="mail-template-head">
        <span className="dash-eyebrow">How the emails look</span>
        <span className="dash-quiet">One choice for the org: every agent's emails are sent this way.</span>
        <div className="dash-switch" role="group" aria-label="How the org's emails are set">
          {MODES.map((one) => (
            <button key={one.mode} type="button" className={mode === one.mode ? "dash-switch-on" : ""} aria-pressed={mode === one.mode} title={one.says} onClick={() => (one.mode === "html" && (mode === "simple" || html.trim() === "") && setHtml(templateOf(simple)), setMode(one.mode), setSaid(null))}>
              {one.name}
              {kept === one.mode ? " ·" : ""}
            </button>
          ))}
        </div>
      </header>
      <p className="num-hint mail-template-says">
        {chosen?.says} {kept === mode ? "This is how they are sent now." : "Not saved yet."}
      </p>
      <div className="mail-template-body">
        <div className="mail-template-form">
          {mode === "simple" && (
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
          )}
          {mode === "html" && (
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
            <button type="button" className="cfg-save" disabled={busy || !ready || (kept === mode && !templated)} onClick={() => void keep()}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
        {preview.html === null ? (
          <pre className="mail-template-preview mail-text-preview" aria-label="The reply as a contact would read it">{preview.text}</pre>
        ) : (
          <iframe className="mail-frame mail-template-preview" title="The reply as a contact would read it" sandbox="" srcDoc={preview.html} />
        )}
      </div>
    </section>
  );
}

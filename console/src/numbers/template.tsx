/** A WhatsApp number's template form: the one message that opens a conversation there, sent from production and only answered in the sandbox. */

import { useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { WORLD } from "../lib/world";
import { sendTemplate, type Templated } from "./door";
import { e164, shown } from "./words";

/** What became of the last one, as a line: where it went and Meta's id, or that the sandbox sent nothing. */
function said(sent: Templated): string {
  const onTheirs = sent.call == null ? "" : " Its words opened their conversation, in Calls.";
  if (sent.simulated) return `Simulated: ${sent.template} would go to ${shown(sent.to)}. Nothing was sent.${onTheirs}`;
  return `Sent ${sent.template} to ${shown(sent.to)}${sent.from == null ? "" : ` from ${shown(sent.from)}`} · ${sent.message_id ?? "said on their open conversation"}.${onTheirs}`;
}

/** `agent` answers WhatsApp at `number`: the template leaves from it. */
export function SendTemplate({ agent, number }: { agent: string; number: string }): ReactNode {
  const credentials = useCredentials();
  const [to, setTo] = useState("");
  const [template, setTemplate] = useState("");
  const [language, setLanguage] = useState("");
  const [variables, setVariables] = useState("");
  const [words, setWords] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<Templated | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const real = WORLD === "production";
  const ready = to.trim() !== "" && template.trim() !== "" && language.trim() !== "";

  const send = async (): Promise<void> => {
    setBusy(true);
    setRefused(null);
    setSent(null);
    try {
      // One variable a line, in the order the template's {{1}}, {{2}}… take them.
      const filled = variables.split("\n").map((line) => line.trim()).filter((line) => line !== "");
      // Its words, when given, are the first message of the contact's conversation: their answer lands after them.
      const said = words.trim() === "" ? {} : { text: words.trim() };
      setSent(await sendTemplate(credentials, agent, { to: e164(to), template: template.trim(), language: language.trim(), variables: filled, from: number, ...said }));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (!real) void send();
  };

  return (
    <section className="dash-card num-card">
      <span className="dash-eyebrow dash-eyebrow-head">Write first with a template</span>
      <p className="dash-quiet num-template-about">
        Outside the 24 hours after a contact's last message, WhatsApp lets {agent} write only a template Meta approved, and Meta charges the number's account for it.{" "}
        {real ? "Here it is sent for real." : "In the sandbox nothing is sent: the answer says what would have gone."}
      </p>
      <form className="num-template" onSubmit={submit}>
        <input className="cfg-input" aria-label="To" placeholder="To: +1 415 555 0142" required autoComplete="off" value={to} onChange={(event) => setTo(event.target.value)} />
        <input className="cfg-input" aria-label="Template" placeholder="Template: visit_reminder" required spellCheck={false} autoComplete="off" value={template} onChange={(event) => setTemplate(event.target.value)} />
        <input className="cfg-input num-template-language" aria-label="Language" placeholder="Language: en_US" required spellCheck={false} autoComplete="off" value={language} onChange={(event) => setLanguage(event.target.value)} />
        <textarea className="cfg-input cfg-area num-template-variables" rows={3} aria-label="Variables" placeholder={"What fills {{1}}, {{2}}…, one a line"} value={variables} onChange={(event) => setVariables(event.target.value)} />
        <textarea className="cfg-input cfg-area num-template-variables" rows={2} aria-label="What it says" placeholder="What it says once filled (optional): the first message of their conversation, so their answer reaches the agent after it" value={words} onChange={(event) => setWords(event.target.value)} />
        {real ? (
          ready && !busy && <ConfirmButton label="Send it" asks="Send it? Meta charges it" onConfirm={() => void send()} />
        ) : (
          <button type="submit" className="app-button" disabled={busy || !ready}>
            {busy ? "Asking…" : "Try it"}
          </button>
        )}
      </form>
      {sent !== null && <p className="dash-quiet num-template-said">{said(sent)}</p>}
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}
    </section>
  );
}

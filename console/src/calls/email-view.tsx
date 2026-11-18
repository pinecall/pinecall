/** An email call read as a mailbox reads it: the thread's subject, then each email, the agent's as its contact received it, set in the org's layout. */

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { post } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { Face } from "./face";
import { lettersFor } from "./format";
import "./email.css";

/** One email of the thread: who wrote it, when, and its words. */
interface Mail {
  seq: number;
  at: number;
  mine: boolean;
  text: string;
}

function mailsOf(entries: readonly Entry[]): Mail[] {
  return entries.flatMap((entry): Mail[] => {
    if (entry.ephemeral || (entry.type !== "turn.user" && entry.type !== "turn.agent")) return [];
    const text = Reflect.get(Object(entry.data), "text");
    return typeof text === "string" && text.trim() !== "" ? [{ seq: entry.seq, at: entry.ts, mine: entry.type === "turn.agent", text }] : [];
  });
}

// What the call was opened on: the subject the contact wrote, which the reply answers under.
function subjectOf(entries: readonly Entry[]): string {
  const started = entries.find((entry) => entry.type === "call.started");
  const metadata = started === undefined ? undefined : Reflect.get(Object(started.data), "metadata");
  const subject = metadata === undefined ? undefined : Reflect.get(Object(metadata), "subject");
  return typeof subject === "string" && subject.trim() !== "" ? subject : "No subject";
}

const when = (at: number): string => new Date(at * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

// The first words of an email, for one folded in the thread.
const snippetOf = (text: string): string => text.replace(/\s+/g, " ").trim().slice(0, 140);

/** The agent's reply as the contact read it: the org's layout around its words, asked of the gateway, which sends nothing. */
function AgentMail({ text, subject }: { text: string; subject: string }): ReactNode {
  const credentials = useCredentials();
  const [html, setHtml] = useState<string | null>(null);
  const [height, setHeight] = useState(160);
  useEffect(() => {
    let current = true;
    void post(credentials, "/v1/org/email/layout/preview", { text, subject })
      .then((answer) => {
        const set = Reflect.get(Object(answer), "html");
        if (current && typeof set === "string") setHtml(set);
      })
      .catch(() => current && setHtml(null));
    return () => {
      current = false;
    };
  }, [credentials, text, subject]);
  if (html === null) return <div className="mail-text">{text}</div>;
  return (
    <iframe
      className="mail-frame"
      title="The reply as the contact read it"
      // No script runs in it: the layout is the org's, and the words were escaped where they were set in.
      sandbox="allow-same-origin"
      srcDoc={html}
      style={{ height }}
      onLoad={(event) => setHeight(Math.max(120, event.currentTarget.contentDocument?.body.scrollHeight ?? 160) + 8)}
    />
  );
}

export function EmailView({ entries, state }: { entries: Entry[]; state: State }): ReactNode {
  const mails = useMemo(() => mailsOf(entries), [entries]);
  const subject = useMemo(() => subjectOf(entries), [entries]);
  const caller = state.caller;
  const contactName = caller?.name ?? caller?.email ?? state.from ?? "The contact";
  const contactAddress = caller?.email ?? state.from ?? "";
  const mailbox = state.to ?? "";
  // The newest email is open, as a mail client opens a thread; the others fold to a line, opened by a click.
  const [opened, setOpened] = useState<ReadonlySet<number>>(new Set());
  const newest = mails.at(-1)?.seq;
  const reply = subject.toLowerCase().startsWith("re:") ? subject : `Re: ${subject}`;

  return (
    <div className="calls-scroll">
      <div className="mail-thread">
        <header className="mail-head">
          <h2 className="mail-subject">{subject}</h2>
          <span className="mail-count">
            {mails.length} {mails.length === 1 ? "email" : "emails"} · {mailbox}
          </span>
        </header>
        {mails.length === 0 && <p className="dash-quiet mail-none">Nothing written yet.</p>}
        {mails.map((mail) => {
          const open = mail.seq === newest || opened.has(mail.seq);
          const name = mail.mine ? "The agent" : contactName;
          const address = mail.mine ? mailbox : contactAddress;
          return (
            <article key={mail.seq} className={open ? "mail-card mail-card-open" : "mail-card"} data-seq={mail.seq}>
              <button type="button" className="mail-card-head" aria-expanded={open} onClick={() => setOpened((was) => (mail.seq === newest ? was : was.has(mail.seq) ? new Set([...was].filter((one) => one !== mail.seq)) : new Set(was).add(mail.seq)))}>
                <Face name={name} letters={mail.mine ? "A" : lettersFor(caller?.name, contactAddress)} />
                <span className="mail-who">
                  <span className="mail-name">{name}</span>
                  <span className="mail-address">{open ? `${address} · to ${mail.mine ? contactAddress : mailbox}` : snippetOf(mail.text)}</span>
                </span>
                <span className="mail-when">{when(mail.at)}</span>
              </button>
              {open && <div className="mail-body">{mail.mine ? <AgentMail text={mail.text} subject={reply} /> : <div className="mail-text">{mail.text}</div>}</div>}
            </article>
          );
        })}
      </div>
    </div>
  );
}

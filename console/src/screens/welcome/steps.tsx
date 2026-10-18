/** The guide's first and last steps, and the code: what Pinecall gives, what an agent is, and going live. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import type { Limits } from "@pinecall/core/wire/rest-org";
import { CODE, FILE, LANGUAGES, READS, type Language } from "./agent-code";
import { Command } from "./command";
import { highlighted } from "./highlight";

export function Gives({ limits, world }: { limits: Limits | null; world: string }): ReactNode {
  const free = limits !== null && limits.minutes.limit !== null ? limits.minutes.limit : null;
  const lent = limits !== null && (limits.lends === null || limits.lends.length > 0);
  return (
    <>
      <p className="wel-lead">
        You write an agent as a class, in your own code. Pinecall answers the phone with it: it hears the caller, runs your class, and speaks the answer. This guide
        takes about ten minutes and ends with your agent on a real call.
      </p>
      <div className="wel-facts">
        <div className="wel-fact">
          <strong>{free === null ? "No minute limit" : `${free} free minutes`}</strong>
          <span>{free === null ? `Your ${world} has no limit on call minutes.` : `of calls a month in your ${world}, starting again on the 1st. Chats and simulations use none.`}</span>
        </div>
        <div className="wel-fact">
          <strong>{lent ? "Nothing else to sign up for" : "Your own vendor keys"}</strong>
          <span>
            {lent ? "The model, the speech recognition and the voice run on Pinecall's keys. You can use your own later, under " : "Your calls run on keys you add under "}
            <Link to="/providers">Providers</Link>.
          </span>
        </div>
        <div className="wel-fact">
          <strong>A safe copy first</strong>
          <span>Everything here is the sandbox: a real agent on real calls, but only yours. Production is a step you take on purpose.</span>
        </div>
      </div>
    </>
  );
}

export function CodeStep({ language, onLanguage }: { language: Language; onLanguage: (language: Language) => void }): ReactNode {
  return (
    <>
      <p className="wel-lead">
        An agent is a class. This one is whole: it answers from the business's documents and takes a message otherwise. Pinecall writes it for you in the next step; you change it
        as you like.
      </p>
      <div className="wel-panel">
        <div className="wel-panel-head">
          <span className="wel-panel-tabs" role="tablist">
            {LANGUAGES.map((one) => (
              <button key={one.value} type="button" role="tab" aria-selected={one.value === language} className="wel-panel-tab" onClick={() => onLanguage(one.value)}>
                {one.label}
              </button>
            ))}
          </span>
          <span className="wel-panel-file">{FILE[language]}</span>
        </div>
        <pre className="wel-panel-body">{highlighted(CODE[language], language)}</pre>
      </div>
      <ul className="wel-reads">
        {READS[language].map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="wel-hint">Nothing to install yet: this step is only to see what you will be writing.</p>
    </>
  );
}

export function Ready({ world }: { world: string }): ReactNode {
  return (
    <>
      <p className="wel-lead">
        Your agent runs while your computer does. To have it answer customers all the time, run the same project on a server of yours, in production. It needs one thing your
        computer had from <code className="wel-inline">pinecall login</code>: a key, this time the server's own.
      </p>
      <div className="wel-facts">
        <div className="wel-fact">
          <strong>1 · Make the server's key</strong>
          <span>
            In <Link to="/tokens">API keys</Link>, make one for that server, and put it in its environment as <code className="wel-inline">PINECALL_KEY</code>. It belongs to the
            org, so it keeps working when whoever made it leaves.
          </span>
        </div>
        <div className="wel-fact">
          <strong>2 · Run it there</strong>
          <span>The same command you ran here, for production. Any server that can reach this gateway will do: a VM, a container, your existing backend.</span>
        </div>
      </div>
      <Command line="pinecall start --prod" say="on your server, in the project's folder" />
      <div className="wel-facts">
        <div className="wel-fact">
          <strong>Production is separate</strong>
          <span>Its own minutes, its own settings and its own numbers. Nothing you try in the sandbox touches it.</span>
        </div>
        <div className="wel-fact">
          <strong>Where to look next</strong>
          <span>
            <Link to="/calls">Calls</Link> for every conversation as it happens, <Link to="/quality">Quality</Link> for how the judges score them, and the <b>Get started</b> list on your
            Overview for what is left to do in {world}.
          </span>
        </div>
      </div>
    </>
  );
}

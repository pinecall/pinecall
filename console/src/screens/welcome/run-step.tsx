/** Step: the agent running on the person's computer, by the CLI or their AI assistant, and the page waiting until it connects. */

import type { ReactNode } from "react";

import type { HeldAgent } from "@pinecall/core/wire/rest-org";
import { SLUG, type Language } from "./agent-code";
import { OnYourComputer } from "./on-your-computer";

export function RunStep({ language, agents }: { language: Language; agents: HeldAgent[] }): ReactNode {
  const ours = agents.find((one) => one.slug === SLUG) ?? agents[0];
  return (
    <>
      <p className="wel-lead">
        An agent answers only while it runs somewhere. While you build it, that is your computer: your code, your terminal, every change the moment you save. Pinecall sends it
        the calls.
      </p>
      <OnYourComputer language={language} />
      {ours === undefined ? (
        <div className="wel-waiting">
          <span className="wel-dot" /> Waiting for your agent. When <code className="wel-inline">pinecall start</code> runs, this turns green by itself and the next steps open.
        </div>
      ) : (
        <div className="wel-waiting wel-waiting-ok">✓ {ours.slug} is running on your computer and connected to this org.</div>
      )}
    </>
  );
}

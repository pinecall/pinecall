/** The other way to run the agent: on the person's own computer, by four commands or by asking their AI assistant. */

import { useState, type ReactNode } from "react";

import { LANGUAGES, SLUG, type Language } from "./agent-code";
import { Terminal } from "./terminal";

type Way = "terminal" | "assistant";

export function OnYourComputer({ language }: { language: Language }): ReactNode {
  const [way, setWay] = useState<Way>("terminal");
  const flag = LANGUAGES.find((one) => one.value === language)?.flag ?? "";
  const label = LANGUAGES.find((one) => one.value === language)?.label ?? "";
  return (
    <>
      <p className="wel-hint">
        Three things make it work: the CLI installed, this computer signed in to your org (the browser asks you to confirm), and the project linked to it, which is what gives it
        its key. You never make a key by hand.
      </p>
      <div className="wel-ways" role="tablist">
        <button type="button" role="tab" aria-selected={way === "terminal"} className="wel-way" onClick={() => setWay("terminal")}>
          <strong>In a terminal</strong>
          <span>Four commands, with the CLI.</span>
        </button>
        <button type="button" role="tab" aria-selected={way === "assistant"} className="wel-way" onClick={() => setWay("assistant")}>
          <strong>With your AI assistant</strong>
          <span>Claude Code, Cursor, Codex: ask it, and it does the four.</span>
        </button>
      </div>
      {way === "terminal" ? (
        <Terminal
          lines={[
            { say: "install the CLI, once", run: "npm i -g pinecall" },
            { say: "sign this computer in to your org: it opens this console to confirm", run: `pinecall login ${window.location.origin}` },
            { say: `write the ${label} agent from the step before into a folder, and link it: this makes the project's key`, run: `pinecall new ${SLUG}${flag} && cd ${SLUG} && pinecall link` },
            { say: "run it: it answers for as long as this runs, and prints a link to talk to it", run: "pinecall start" },
          ]}
        />
      ) : (
        <>
          <Terminal lines={[{ say: "install the CLI and register its MCP server with every assistant on this computer", run: "npm i -g pinecall && pinecall mcp install" }]} />
          <div className="wel-block">
            <strong>Then tell your assistant</strong>
            <blockquote className="wel-quote">
              Make me a Pinecall agent in ./{SLUG}, in {label}, that answers from the business's documents and takes a message otherwise. Sign in at {window.location.origin},
              link it to my org, and start it.
            </blockquote>
            <span className="wel-hint">Its tools sign the machine in, write the project, link it and start it. No key ever passes through the assistant.</span>
          </div>
        </>
      )}
    </>
  );
}

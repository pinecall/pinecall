/** Studio in production: the release answering there, read and never edited — the sandbox is where it changes. */

import type { ReactNode } from "react";

import { dayAndTime } from "../../lib/format";
import { inTheOtherWorld } from "../../lib/mode";
import { Button, Card, CardHead, Empty, Page, PageHead } from "../../ui";
import type { StudioAgent } from "./door";
import { greetingText, openingOf } from "./draft";

export function Answering({ agent }: { agent: StudioAgent }): ReactNode {
  const { definition } = agent;
  const opening = openingOf(definition.greeting);
  return (
    <Page width={900}>
      <PageHead
        title={agent.name}
        lede={`Release ${agent.release} answers in production · deployed by ${agent.author} · ${dayAndTime(agent.saved_at)}${agent.stopped ? " · stopped" : ""}`}
        actions={
          <Button size="md" onClick={() => window.location.assign(inTheOtherWorld(window.location.pathname))}>
            Open it in the sandbox
          </Button>
        }
      />
      <p className="sto-hint">Edit it in the sandbox, then Deploy.</p>

      <Card>
        <CardHead title="Instructions" />
        <pre className="ui-code sto-read">{definition.instructions}</pre>
      </Card>

      <Card>
        <CardHead title="Greeting" />
        <div className="sto-body">
          {opening === "none" && <p className="sto-hint">The caller speaks first.</p>}
          {opening === "say" && <p>Says: “{greetingText(definition.greeting)}”</p>}
          {opening === "reply" && <p>The model opens the call from: “{greetingText(definition.greeting)}”</p>}
        </div>
      </Card>

      <Card>
        <CardHead title="Tools" meta={definition.tools.length === 1 ? "1 tool" : `${definition.tools.length} tools`} />
        {definition.tools.length === 0 ? (
          <Empty>No tool.</Empty>
        ) : (
          <div className="sto-body">
            {definition.tools.map((tool) => (
              <div key={tool.name} className="sto-summary">
                <div>
                  <span className="ui-fixed sto-tool-name">{tool.name}</span> <span className="ui-fixed sto-hint">{tool.method} {tool.url}</span>
                </div>
                <div className="sto-hint">{tool.description}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHead title="Data collection" />
        <div className="sto-body">
          {definition.collect === null || definition.collect === undefined ? (
            <p className="sto-hint">Off.</p>
          ) : (
            <>
              <p>
                Collects {definition.collect.fields.map((field) => `${field.name}${field.required ? "" : " (optional)"}`).join(", ")}
                {definition.collect.end_when_done ? ", and ends the call once the required ones are in." : "."}
              </p>
              {(definition.collect.send_to ?? "") !== "" && <p className="sto-hint">Sends the results to {definition.collect.send_to}.</p>}
            </>
          )}
        </div>
      </Card>
    </Page>
  );
}

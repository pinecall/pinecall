/** Studio: an agent built with no code — edited in the sandbox beside a live preview, read in production. */

import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router";

import { GatewayError, saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { WORLD } from "../../lib/mode";
import { Card, Page, PageHead } from "../../ui";
import { readStudioAgent, type StudioAgent } from "./door";
import { Editor } from "./editor";
import { Answering } from "./production";
import "./studio.css";

const NOT_FOUND = 404;
const IS_CODE = 400;

/** What the screen says instead of the editor when the gateway refused to read the agent. */
function refusal(failed: unknown): string {
  if (failed instanceof GatewayError && failed.status === NOT_FOUND) {
    return WORLD === "sandbox"
      ? "This agent is not built in Studio."
      : "This agent is not built in Studio, or has not been deployed to production from it yet.";
  }
  if (failed instanceof GatewayError && failed.status === IS_CODE) return "This agent is code: its class is what to edit.";
  return saidBy(failed);
}

export function Studio(): ReactNode {
  const agent = useParams()["agent"] ?? "";
  const credentials = useCredentials();
  const [standing, setStanding] = useState<StudioAgent | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    setStanding(null);
    setRefused(null);
    readStudioAgent(credentials, agent).then(
      (read) => {
        if (!gone) setStanding(read);
      },
      (failed: unknown) => {
        if (!gone) setRefused(refusal(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials, agent]);

  if (refused !== null) {
    return (
      <Page width={760}>
        <PageHead title="Studio" />
        <Card pad>
          <p className="sto-refused">{refused}</p>
        </Card>
      </Page>
    );
  }
  if (standing === null) return null;
  // Keyed by the agent: another agent picked in the sidebar is another form, never this one's draft.
  return WORLD === "sandbox" ? <Editor key={standing.name} initial={standing} /> : <Answering agent={standing} />;
}

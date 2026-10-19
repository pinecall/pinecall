/** Studio with no agent in view: the agents the org built in it, and the way to build another — made in the sandbox, which production sends you to. */

import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { inTheOtherWorld, WORLD } from "../../lib/mode";
import { useScopes } from "../../lib/whoami";
import { Button, Empty, Icon, Page, PageHead, Pill, Refused } from "../../ui";
import { readStudioAgents, type StudioAgent } from "./door";
import { NewAgent } from "./new-agent";

// A link from production names the form to open: `?new=1` is the sandbox's Studio with it already there.
const OPEN_FORM = "?new=1";

export function StudioHome(): ReactNode {
  const credentials = useCredentials();
  const scopes = useScopes();
  const [agents, setAgents] = useState<StudioAgent[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [making, setMaking] = useState(() => WORLD === "sandbox" && new URLSearchParams(window.location.search).get("new") === "1");
  // An agent built in Studio is made in the sandbox, by a key that may run the org's apps.
  const canMake = WORLD === "sandbox" && scopes !== null && scopes.includes("app");

  useEffect(() => {
    let gone = false;
    readStudioAgents(credentials).then(
      (read) => {
        if (!gone) setAgents(read);
      },
      (failed: unknown) => {
        if (!gone) setRefused(saidBy(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return (
    <Page width={900}>
      <PageHead
        title="Studio"
        lede="Build an agent with no code: what it is told, how it opens a call, the requests it may make and what it collects. It answers in the sandbox first, and Deploy puts it in production."
        actions={
          WORLD === "production" ? (
            <Button kind="primary" onClick={() => window.location.assign(`${inTheOtherWorld(window.location.pathname)}${OPEN_FORM}`)}>
              New agent in the sandbox
            </Button>
          ) : (
            canMake && (
              <Button kind="primary" onClick={() => setMaking(true)} disabled={making}>
                New agent
              </Button>
            )
          )
        }
      />
      {making && <NewAgent onCancel={() => setMaking(false)} />}
      <Refused>{refused}</Refused>
      {WORLD === "sandbox" && !canMake && <p className="sto-hint">A key that may run the org&apos;s apps builds agents here.</p>}
      {agents !== null && agents.length === 0 && <Empty>{WORLD === "sandbox" ? "No agent has been built in Studio yet. New agent makes the first." : "Nothing built in Studio answers in production yet. Build one in the sandbox, then Deploy it."}</Empty>}
      {agents !== null && agents.length > 0 && (
        <div className="sto-home">
          {agents.map((one) => (
            <Link key={one.name} to={`/a/${encodeURIComponent(one.name)}/studio`} className="sto-home-row">
              <span className="sto-home-icon" aria-hidden>
                <Icon name="bot" size={18} />
              </span>
              <span className="sto-home-words">
                <span className="sto-home-name">{one.name}</span>
                <span className="sto-home-sub">
                  Release {one.release} · saved by {one.author} · {dayAndTime(one.saved_at)}
                </span>
              </span>
              {one.stopped && (
                <Pill tone="gray" small>
                  stopped
                </Pill>
              )}
              <span className="sto-home-go" aria-hidden>
                <Icon name="chevron" size={14} />
              </span>
            </Link>
          ))}
        </div>
      )}
    </Page>
  );
}

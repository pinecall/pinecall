/** Nothing running: what the Agents screen draws in place of its list while no agent of the org is up. */

import type { ReactNode } from "react";

import { Button, ButtonLink, Command, Icon, Nothing } from "../../ui";

const FIRST_AGENT = "https://docs.pinecall.io/start/your-first-agent";

// A sketch of the list the screen will hold: an agent per row, its name, its doors, a call live.
const ROWS = [
  { name: 46, doors: 2, live: true },
  { name: 34, doors: 1, live: false },
  { name: 40, doors: 3, live: false },
] as const;

function Sketch(): ReactNode {
  return (
    <div className="agents-none-art">
      {ROWS.map((row, index) => (
        <div key={index} className="agents-none-row">
          <span className="agents-none-avatar" />
          <span className="agents-none-name" style={{ width: `${row.name}%` }} />
          <span className="agents-none-doors">
            {Array.from({ length: row.doors }, (_, door) => (
              <i key={door} />
            ))}
          </span>
          <span className={row.live ? "agents-none-dot agents-none-dot-live" : "agents-none-dot"} />
        </div>
      ))}
    </div>
  );
}

/** In the sandbox the way forward is to make one; in production, to deploy one. */
export function NothingRunning({ world, onMake }: { world: "sandbox" | "production"; onMake: (() => void) | null }): ReactNode {
  if (world === "production")
    return (
      <Nothing
        art={<Sketch />}
        title="Nothing is answering in production yet"
        actions={
          <>
            <Command run="pinecall deploy --prod" />
            <ButtonLink to="/apps">
              <Icon name="server" size={14} />
              Open Apps
            </ButtonLink>
          </>
        }
      >
        An agent shows up here the moment it goes live for your customers: deploy it to Pinecall from your project&apos;s folder, or start it on your own server with a server token.
      </Nothing>
    );
  return (
    <Nothing
      art={<Sketch />}
      title="No agent is running yet"
      actions={
        <>
          {onMake !== null && (
            <Button kind="primary" onClick={onMake}>
              <Icon name="bot" size={14} />
              New agent
            </Button>
          )}
          <Command run="pinecall start" />
        </>
      }
    >
      An agent shows up here the moment it starts. Make one in Studio with no code, or write it in code and start it from your project&apos;s folder.{" "}
      <a href={FIRST_AGENT} target="_blank" rel="noreferrer">
        Build your first agent
      </a>
    </Nothing>
  );
}

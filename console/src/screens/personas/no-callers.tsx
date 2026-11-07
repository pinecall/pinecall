/** No callers yet: what Personas draws while the roster is empty — Pinecall's callers to come, and the way to them. */

import type { ReactNode } from "react";

import { WORLD } from "../../lib/mode";
import { Button, ButtonLink, Icon, Nothing } from "../../ui";
import { Face, THE_LIBRARY } from "./face";

// The callers a real day brings, first: the red team is the library's too, and named in the words.
const SHOWN = 7;

function Sketch(): ReactNode {
  return (
    <div className="psn-none-art">
      {THE_LIBRARY.slice(0, SHOWN).map((name) => (
        <span key={name} className="psn-none-one">
          <Face name={name} size={44} />
          <span className="psn-none-name">{name}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * Pinecall's callers are switched per agent and read through one: with no agent the roster cannot
 * show them yet, and the way forward is an agent; with one, writing a caller of your own.
 */
export function NoCallers({ agent, agents, onNew, onGenerate }: { agent: string; agents: number; onNew: () => void; onGenerate: () => void }): ReactNode {
  if (agents === 0)
    return (
      <Nothing
        art={<Sketch />}
        title="Callers to test your agents with"
        actions={
          <ButtonLink kind="primary" to="/agents">
            <Icon name="bot" size={14} />
            {WORLD === "sandbox" ? "Make your first agent" : "Open Agents"}
          </ButtonLink>
        }
      >
        A persona is a caller a model plays against your agent: what they want, how they talk, what they know. Pinecall brings {THE_LIBRARY.length} ready to switch on — in a hurry, elderly and slow, talking over the agent, angry, and a red team that tries to leak your prompt — and you can write your own. They show up here as soon as you have an agent.
      </Nothing>
    );
  return (
    <Nothing
      art={<Sketch />}
      title="No callers yet"
      actions={
        <>
          <Button kind="primary" onClick={onNew}>
            <Icon name="persona" size={14} />
            New persona
          </Button>
          {agent !== "" && (
            <Button onClick={onGenerate}>
              <Icon name="bulb" size={14} />
              Generate from {agent}
            </Button>
          )}
        </>
      }
    >
      A persona is a caller a model plays against your agent: what they want, how they talk, what they know about themselves. There is no script — it improvises every line, in writing or out loud.
    </Nothing>
  );
}

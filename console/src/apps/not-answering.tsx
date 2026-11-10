/** What an agent's tab says while the gateway is not answering for it: stopped, failed, still starting, or never able to start; and the one move that fits. */

import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "./confirm";
import { removeApp, startApp } from "./door";
import type { App } from "./fold";

// An app the gateway made this recently is still coming up.
const STARTING_S = 30;

/** The tabs that read the agent as it runs: with nobody holding it, each would only say the gateway's refusal. */
export const NEEDS_IT_ANSWERING: ReadonlySet<string> = new Set(["configure", "advanced", "knowledge", "test", "setup"]);

/** Whether the gateway holds the agent now; what it hosts and does not hold answers no door of the agent's. */
export const isAnswering = (app: App): boolean => app.held !== null;

export function NotAnswering({ app, base, onChanged, onRemoved }: { app: App; base: string; onChanged: () => void; onRemoved: () => void }): ReactNode {
  const credentials = useCredentials();
  const [refused, setRefused] = useState<string | null>(null);
  const { hosted, name } = app;
  const act = (doing: () => Promise<void>, then: () => void): void => {
    setRefused(null);
    doing().then(then, (failed: unknown) => setRefused(saidBy(failed)));
  };
  if (hosted === null) return null;
  const young = Date.now() / 1000 - hosted.created_at < STARTING_S;
  const said = hosted.stopped
    ? { title: `${name} is stopped`, says: "Start it, and its settings and tests open here." }
    : hosted.failed_why !== null
      ? { title: `Release ${hosted.release ?? ""} of ${name} did not start`, says: "Its overview says why. Deploy a release that starts, and this opens." }
      : hosted.kind === "code" || young
        ? { title: `${name} is starting`, says: "This opens as soon as it answers." }
        : { title: `The gateway could not start ${name}`, says: "The usual reason is its name: a name belongs to one organization across all of Pinecall, and another already uses this one. Remove it and make it again under another name." };
  return (
    <div className="app-empty">
      <h2 className="app-name">{said.title}</h2>
      <p className="dash-quiet">{said.says}</p>
      {refused !== null && <p className="app-refused">{refused}</p>}
      <div className="app-actions">
        {hosted.stopped && (
          <button type="button" className="cfg-save" onClick={() => act(() => startApp(credentials, name), onChanged)}>
            Start
          </button>
        )}
        {!hosted.stopped && hosted.failed_why !== null && (
          <Link to={`${base}/${encodeURIComponent(name)}`} className="app-button">
            See why
          </Link>
        )}
        {!hosted.stopped && hosted.failed_why === null && hosted.kind === "studio" && !young && <ConfirmButton label="Remove it" asks="Remove it for good?" danger onConfirm={() => act(() => removeApp(credentials, name), onRemoved)} />}
      </div>
    </div>
  );
}

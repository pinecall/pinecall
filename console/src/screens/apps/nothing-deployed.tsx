/** Nothing deployed: what Apps draws in place of its table while the org hosts no app in this world. */

import type { ReactNode } from "react";

import { Command, Nothing } from "../../ui";

const DEPLOY = "https://docs.pinecall.io/guides/deploy";

// A sketch of the releases to come: the newest serving, the ones before it kept to roll back to.
const RELEASES = [
  { note: 52, serving: true },
  { note: 38, serving: false },
  { note: 44, serving: false },
] as const;

function Sketch(): ReactNode {
  return (
    <div className="apps-none-art">
      {RELEASES.map((release, index) => (
        <div key={index} className="apps-none-row">
          <span className="apps-none-number">{RELEASES.length - index}</span>
          <span className="apps-none-note" style={{ width: `${release.note}%` }} />
          <span className={release.serving ? "apps-none-pill apps-none-serving" : "apps-none-pill"} />
        </div>
      ))}
    </div>
  );
}

export function NothingDeployed({ world }: { world: "sandbox" | "production" }): ReactNode {
  return (
    <Nothing art={<Sketch />} title={`Nothing deployed to ${world} yet`} actions={<Command run={world === "production" ? "pinecall deploy --prod" : "pinecall deploy"} />}>
      Deploy an agent and Pinecall keeps it running for you, with no server of your own. Run this in your project&apos;s folder; an agent made in Studio deploys from Studio.{" "}
      <a href={DEPLOY} target="_blank" rel="noreferrer">
        How deploying works
      </a>
    </Nothing>
  );
}

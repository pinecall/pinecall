/** An agent's name, a link to where its knowledge is set when the gateway knows which kind it is. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { useOrg } from "../lib/org";

export function AgentLink({ name, className }: { name: string; className: string }): ReactNode {
  const { agents } = useOrg();
  const held = agents.find((one) => one.slug === name);
  if (held === undefined) return <span className={className}>{name}</span>;
  const at = encodeURIComponent(name);
  return (
    <Link className={className} to={held.kind === "studio" ? `/agents/${at}/knowledge` : `/apps/${at}/setup`}>
      {name}
    </Link>
  );
}

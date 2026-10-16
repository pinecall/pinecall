/** Under a row a judge broke on: the judge's creature, its name, and why, in red. */

import type { ReactNode } from "react";

import { Creature } from "../quality/creature";
import type { Broke } from "./broken";

export function BrokenBy({ broke }: { broke: readonly Broke[] }): ReactNode {
  return (
    <div className="call-broken-by">
      {broke.map((one) => (
        <div key={one.judge} className="call-broken-judge">
          <Creature name={one.judge} size={24} />
          <span className="call-broken-name">{one.judge}</span>
          <span className="call-broken-why">{one.reason}</span>
        </div>
      ))}
    </div>
  );
}

/** Shown when the person's org does not allow them in production. */

import type { ReactNode } from "react";

import { inTheWorld, WORLD_BASE } from "../../lib/mode";
import { forgetKey } from "../../lib/session-key";
import { TextAction } from "../../ui";
import { WayIn } from "./way-in";

/** Explains why, opens the sandbox — the same page under `/sandbox`, on the same key — and offers another sign-in. */
export function NoProduction({ said }: { said: string }): ReactNode {
  const leave = (): void => {
    void forgetKey();
    window.location.assign(WORLD_BASE);
  };
  const openTheSandbox = (): void => window.location.assign(inTheWorld("sandbox", "/"));
  return (
    <WayIn foot={<>The sandbox is open to you: it is where things are tried before the public sees them.</>}>
      <h1 className="login-title">No production access</h1>
      <p className="login-lede">{said}</p>
      <TextAction onClick={openTheSandbox}>Open the sandbox</TextAction>
      <TextAction onClick={leave}>Sign in as somebody else</TextAction>
    </WayIn>
  );
}

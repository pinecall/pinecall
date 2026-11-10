/** Shown when the person's org does not allow them in production. */

import type { ReactNode } from "react";

import { inWorld, WORLD_BASE } from "../lib/world";
import { forgetKey } from "../lib/key";
import { WayIn } from "./way-in";

/** Explains why, opens the sandbox — the same page under `/sandbox`, on the same key — and offers another sign-in. */
export function NoProduction({ said }: { said: string }): ReactNode {
  const leave = (): void => {
    void forgetKey();
    window.location.assign(WORLD_BASE);
  };
  return (
    <WayIn
      title="No production access"
      lede={said}
      aside={
        <>
          <a href={inWorld("sandbox", "/")}>Open the sandbox</a>
          <br />
          <button type="button" className="login-link login-resend" onClick={leave}>
            Sign in as somebody else
          </button>
        </>
      }
      foot={<>The sandbox is open to you: it is where things are tried before the public sees them.</>}
    />
  );
}

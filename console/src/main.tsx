/** Console entry point: resolves the session key (or login/invitation) and mounts the router. */

import { StrictMode, useCallback, useMemo, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { onUnauthorized } from "@pinecall/core/api";
import { followTheSystemTheme } from "@pinecall/core/theme";
import { API_BASE } from "./lib/base";
import { DEVICE } from "./lib/device";
import { CredentialsProvider } from "@pinecall/core/credentials";
import { loginToOrg, loginWithCode, type Signed } from "@pinecall/core/login";
import { forgetThisBrowser } from "./lib/notifier";
import { LeavingProvider } from "./lib/leaving";
import { inTheWorld, WORLD, WORLD_BASE } from "./lib/mode";
import { forgetKey, keepCorner, keepKey, keptCorner, keptKey } from "./lib/session-key";
import { WhoamiProvider } from "./lib/whoami";
import { WorldProvider } from "./lib/world";
import { router } from "./router";
import { Accept, Login } from "./screens/login";
import "./ui/ui.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root for the console to mount in");
}

// CSS already follows the system theme; this only matters after a manual theme toggle.
followTheSystemTheme();

// One-use login code printed by `pinecall console`/`pinecall start`. Removed from the URL before
// render so reloads, bookmarks and screenshots never carry it.
const LOGIN = "login";

// Invitation token stays in the URL until accepted so the card survives a reload.
const INVITATIONS = /^\/invitations\/([^/]+)\/?$/;

function theInvitationInTheAddress(): string | null {
  const found = INVITATIONS.exec(window.location.pathname);
  return found === null ? null : decodeURIComponent(found[1] ?? "");
}

/** The starting key: redeemed from `?login=`, else the stored one, else null. */
async function theKeyToStartWith(): Promise<string | null> {
  const address = new URL(window.location.href);
  const code = address.searchParams.get(LOGIN);
  if (code !== null) {
    address.searchParams.delete(LOGIN);
    window.history.replaceState(null, "", address.toString());
    try {
      const signed = await loginWithCode(API_BASE, code, DEVICE);
      await keepKey(signed.key);
      return signed.key;
    } catch {
      // Spent or expired: fall through to the login screen without saying why.
    }
  }
  return keptKey();
}

/** The app when there is a key, else the login; a dead key falls back to login. */
function Console({ startingWith }: { startingWith: string | null }): ReactNode {
  const [key, setKey] = useState<string | null>(startingWith);
  // Corners exist only in the sandbox.
  const [corner, setCorner] = useState<string | null>(() => (WORLD === "sandbox" ? keptCorner() : null));
  const lookInto = useCallback((other: string | null): void => {
    keepCorner(other);
    setCorner(other);
  }, []);
  // A key the gateway no longer takes is forgotten, and the login asks again.
  onUnauthorized(() => {
    void forgetKey().then(() => setKey(null));
  });

  // Org switch: exchange the key for one in the target org (POST /v1/login/org) and reload at the
  // root, since the current URL belongs to the old org. `landing` is the router's path, so it is
  // placed in this world before the browser is sent there.
  const moveTo = useCallback(
    async (org: string, landing = "/"): Promise<void> => {
      if (key === null) return;
      const signed = await loginToOrg({ base: API_BASE, key }, org);
      keepCorner(null);
      await keepKey(signed.key);
      window.location.assign(inTheWorld(WORLD, landing));
    },
    [key],
  );
  const worlds = useMemo(() => ({ world: WORLD, moveTo, corner, lookInto }), [moveTo, corner, lookInto]);
  // Every request carries its world; the gateway gates production per person (auth/world.py).
  const credentials = useMemo(() => ({ base: API_BASE, key: key ?? "", corner, world: WORLD }), [key, corner]);

  const leave = useCallback((): void => {
    // Unregister push while the key still exists.
    if (key !== null) void forgetThisBrowser({ base: API_BASE, key });
    void forgetKey();
    keepCorner(null);
    setCorner(null);
    setKey(null);
  }, [key]);

  const signed = (proof: Signed): void => {
    void keepKey(proof.key);
    setKey(proof.key);
  };

  if (key === null) {
    const token = theInvitationInTheAddress();
    if (token !== null) {
      return (
        <Accept
          base={API_BASE}
          token={token}
          onSigned={(proof) => {
            // Drop the spent token from the URL: the page lands on this world's home.
            window.history.replaceState(null, "", WORLD_BASE);
            signed(proof);
          }}
        />
      );
    }
    return <Login base={API_BASE} onSigned={signed} />;
  }
  return (
    <CredentialsProvider value={credentials}>
      <WhoamiProvider>
        <WorldProvider value={worlds}>
          <LeavingProvider value={leave}>
            <RouterProvider router={router} />
          </LeavingProvider>
        </WorldProvider>
      </WhoamiProvider>
    </CredentialsProvider>
  );
}

void theKeyToStartWith().then((start) => {
  createRoot(root).render(
    <StrictMode>
      <Console startingWith={start} />
    </StrictMode>,
  );
});

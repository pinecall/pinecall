/** Boots the console: the key this browser keeps, the sign-in when there is none, and the pages. */

import { StrictMode, useCallback, useMemo, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router";

import { onUnauthorized } from "@pinecall/core/api";
import { CredentialsProvider } from "@pinecall/core/credentials";
import { loginWithCode } from "@pinecall/core/login";
import { chooseTheme, chosenTheme, wearTheChosenTheme } from "@pinecall/core/theme";
import { AgentsPage, AppsPage } from "./apps/apps";
import { Dashboard } from "./dashboard/dashboard";
import { CallsPage } from "./dashboard/recent";
import { KnowledgePage } from "./knowledge/knowledge";
import { API_BASE, DEVICE, forgetKey, keepKey, keptKey } from "./lib/key";
import { forgetThisBrowser } from "./lib/notifier";
import { OrgProvider } from "./lib/org";
import { inWorld, pageHere, WORLD, WORLD_BASE } from "./lib/world";
import { Accept, Login, SignUp, Verify, VERIFY } from "./login";
import { Settings } from "./settings/settings";
import { SimulationsPage } from "./simulations/simulations";
import { PageHead } from "./shell/page-head";
import { NotYet, Shell } from "./shell/shell";
import "./base.css";

// Dark until a person picks otherwise: it is a tool people sit in front of all day.
wearTheChosenTheme();
if (chosenTheme() === "auto") chooseTheme("dark");

// A one-use code in the address (`pinecall console`), taken off it before anything is drawn.
const LOGIN = "login";
const INVITATIONS = /^\/invitations\/([^/]+)\/?$/;
const SIGNUP = /^\/signup\/?$/;
const VERIFYING = new RegExp(`^${VERIFY}/?$`);

function theInvitationInTheAddress(): string | null {
  const found = INVITATIONS.exec(window.location.pathname);
  return found === null ? null : decodeURIComponent(found[1] ?? "");
}

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
      // Spent or expired: the sign-in asks.
    }
  }
  return keptKey();
}

const PAGES = ["numbers", "goldens", "personas", "cases", "judges", "quality", "observability", "monitors", "team", "usage", "billing", "privacy", "notifications", "box/orgs", "box/fleet", "box/carriers", "box/routes", "box/traceback", "box/usage", "box/settings"];

function Console({ startingWith }: { startingWith: string | null }): ReactNode {
  const [key, setKey] = useState(startingWith);
  const leave = useCallback((): void => {
    // Unregister this browser's push while the key still exists.
    if (key !== null) void forgetThisBrowser({ base: API_BASE, key });
    void forgetKey();
    setKey(null);
  }, [key]);
  // A key the gateway no longer takes is forgotten, and the sign-in asks again.
  onUnauthorized(leave);

  const credentials = useMemo(() => ({ base: API_BASE, key: key ?? "", world: WORLD }), [key]);
  const router = useMemo(
    () =>
      createBrowserRouter(
        [
          {
            path: "/",
            element: <Shell onLeave={leave} />,
            children: [{ index: true, element: <Dashboard /> }, ...PAGES.map((path) => ({ path, element: <NotYet /> })), { path: "apps", element: <AppsPage /> }, { path: "apps/:app", element: <AppsPage /> }, { path: "apps/:app/:tab", element: <AppsPage /> }, { path: "agents", element: <AgentsPage /> }, { path: "agents/:app", element: <AgentsPage /> }, { path: "agents/:app/:tab", element: <AgentsPage /> }, { path: "knowledge", element: <KnowledgePage /> }, { path: "knowledge/memory", element: <KnowledgePage memory /> }, { path: "knowledge/bases/:base", element: <KnowledgePage /> }, { path: "simulations", element: <SimulationsPage /> }, { path: "simulations/:call", element: <SimulationsPage /> }, { path: "simulations/compare/:comparison", element: <SimulationsPage /> }, { path: "calls", element: <><PageHead /><CallsPage /></> }, { path: "settings", element: <><PageHead /><Settings /></> }, { path: "*", element: <Navigate to="/" replace /> }],
          },
        ],
        { basename: WORLD_BASE },
      ),
    [leave],
  );

  if (key === null) {
    const signed = (proof: { key: string }): void => {
      void keepKey(proof.key);
      setKey(proof.key);
    };
    // A new org opens in the sandbox, whichever world's page it was made on.
    const toTheSandbox = (proof: { key: string }): void => {
      void keepKey(proof.key).then(() => window.location.assign(inWorld("sandbox", "/")));
    };
    const page = pageHere();
    if (SIGNUP.test(page)) return <SignUp base={API_BASE} onMade={toTheSandbox} />;
    if (VERIFYING.test(page)) return <Verify base={API_BASE} onSigned={toTheSandbox} />;
    const token = theInvitationInTheAddress();
    if (token !== null) {
      return (
        <Accept
          base={API_BASE}
          token={token}
          onSigned={(proof) => {
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
      <OrgProvider>
        <RouterProvider router={router} />
      </OrgProvider>
    </CredentialsProvider>
  );
}

const root = document.getElementById("root");
if (root === null) throw new Error("the page has no #root");
const mount = root;

void theKeyToStartWith().then((start) => {
  createRoot(mount).render(
    <StrictMode>
      <Console startingWith={start} />
    </StrictMode>,
  );
});

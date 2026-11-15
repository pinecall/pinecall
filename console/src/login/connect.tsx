/** `/connect`: let an app (an assistant's connector) act as you — the authorization endpoint of the gateway's OAuth. */

import { useEffect, useState, type ReactNode } from "react";
import { z } from "zod";

import { GatewayError, post, read, type Credentials } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { orgsOf, type OrgOf } from "@pinecall/core/login";
import { WayIn } from "./way-in";
import "./login.css";

// What an app's link carries (RFC 6749 section 4.1.1, RFC 7636): the gateway checks every one of them.
interface Asking {
  client_id: string;
  redirect_uri: string;
  code_challenge: string;
  code_challenge_method: string;
  state: string | null;
}

const AskedSchema = z.object({ client_name: z.string(), redirect_host: z.string() });
const ApprovedSchema = z.object({ redirect: z.string(), org: z.string() });
type Asked = z.infer<typeof AskedSchema>;

const THE_PAGE = "/connect";
// /connect opened by hand, or a link cut short.
const NOTHING_ASKED = "Add Pinecall to your assistant as a connector: it opens this page with its own link.";
// A sign-in that leaves the page (Google, an org's provider) comes back to the console's front page:
// what was asked is kept for this tab, for as long as an app waits for its answer.
const KEPT_UNDER = "pinecall.connect";
const KEPT_MS = 10 * 60 * 1000;

function askingIn(search: string): Asking | null {
  const said = new URLSearchParams(search);
  const [client, redirect, challenge] = [said.get("client_id"), said.get("redirect_uri"), said.get("code_challenge")];
  if (client === null || redirect === null || challenge === null) return null;
  return { client_id: client, redirect_uri: redirect, code_challenge: challenge, code_challenge_method: said.get("code_challenge_method") ?? "S256", state: said.get("state") };
}

/** Before a sign-in is drawn: keep what an app asked, so a sign-in that leaves the page finds it again. */
export function keepWhatWasAsked(): void {
  if (window.location.pathname !== THE_PAGE || askingIn(window.location.search) === null) return;
  try {
    window.sessionStorage.setItem(KEPT_UNDER, JSON.stringify({ search: window.location.search, at: Date.now() }));
  } catch {
    // A sign-in that stays on the page needs nothing kept.
  }
}

/** Signed in somewhere else than `/connect` while an app waits: its address, to go back to; null when none does. */
export function whatWasAsked(): string | null {
  try {
    const kept = window.sessionStorage.getItem(KEPT_UNDER);
    window.sessionStorage.removeItem(KEPT_UNDER);
    if (kept === null || window.location.pathname === THE_PAGE) return null;
    const { search, at } = JSON.parse(kept) as { search: string; at: number };
    return Date.now() - at < KEPT_MS ? `${THE_PAGE}${search}` : null;
  } catch {
    return null;
  }
}

async function asked(credentials: Credentials, asking: Asking): Promise<Asked> {
  const { state: _state, ...checked } = asking;
  return AskedSchema.parse(await read(credentials, "/v1/oauth/authorization", checked));
}

/** The app's own address with its code, minted for the person here in the org chosen. */
async function approve(credentials: Credentials, asking: Asking, org: string | null): Promise<string> {
  return ApprovedSchema.parse(await post(credentials, "/v1/oauth/authorization", { ...asking, org })).redirect;
}

// The gateway registered no address a browser would run; a page never follows one all the same.
function send(to: string): void {
  if (new URL(to).protocol === "javascript:") throw new Error("that is no address an app can be sent back to");
  window.location.assign(to);
}

// RFC 6749 section 4.1.2.1: an app told no is sent back saying so, with the state it sent.
function refusalOf(asking: Asking): string {
  const back = new URL(asking.redirect_uri);
  back.searchParams.set("error", "access_denied");
  if (asking.state !== null) back.searchParams.set("state", asking.state);
  back.searchParams.set("iss", window.location.origin);
  return back.toString();
}

const said = (failed: unknown): string => (failed instanceof GatewayError || failed instanceof Error ? failed.message : String(failed));
const nameOf = (org: OrgOf): string => org.name ?? org.slug ?? org.org;

/** Approve an app's request to act as the person here, once they are signed in themselves. */
export function Connect(): ReactNode {
  const credentials = useCredentials();
  const [asking] = useState(() => askingIn(window.location.search));
  const [app, setApp] = useState<Asked | null>(null);
  const [orgs, setOrgs] = useState<OrgOf[]>([]);
  const [org, setOrg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    if (asking === null) return undefined;
    let gone = false;
    asked(credentials, asking).then(
      (found) => !gone && setApp(found),
      (failed: unknown) => !gone && setRefused(said(failed)),
    );
    // A person's own orgs alone: an app is connected where they have a seat.
    orgsOf(credentials).then(
      (found) => {
        if (gone) return;
        const seated = found.filter((one) => one.member !== false && one.status === "active");
        setOrgs(seated);
        setOrg(seated.find((one) => one.here)?.org ?? null);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials, asking]);

  const connect = async (): Promise<void> => {
    if (asking === null) return;
    setBusy(true);
    setRefused(null);
    try {
      send(await approve(credentials, asking, org));
    } catch (failed) {
      setRefused(said(failed));
      setBusy(false);
    }
  };

  if (asking === null) return <WayIn title="No app is asking" lede={NOTHING_ASKED} />;
  if (refused !== null && app === null) return <WayIn title="That link is no good" lede={refused} />;
  const here = orgs.find((one) => one.org === org);
  return (
    <WayIn
      title={app === null ? "Connect to Pinecall?" : `Connect ${app.client_name} to Pinecall?`}
      lede={
        app === null
          ? "Reading who is asking…"
          : `${app.client_name} asks to act as you${here === undefined ? "" : ` in ${nameOf(here)}`}: read and change your agents, their calls and their settings, as you can. You will be sent back to ${app.redirect_host}. Approve it only if you just added Pinecall there yourself.`
      }
      aside="It gets a sign-in of its own, which you end at any time in User settings."
    >
      {orgs.length > 1 && (
        <>
          <label className="login-label" htmlFor="connect-org">
            Workspace
          </label>
          <select id="connect-org" className="login-input" value={org ?? ""} onChange={(event) => setOrg(event.target.value)} disabled={busy}>
            {orgs.map((one) => (
              <option key={one.org} value={one.org}>
                {nameOf(one)}
              </option>
            ))}
          </select>
        </>
      )}
      <button className="login-go" type="button" onClick={() => void connect()} disabled={busy || app === null}>
        {busy ? "Connecting…" : "Connect"}
      </button>
      <button className="login-link" type="button" onClick={() => send(refusalOf(asking))} disabled={busy || app === null}>
        Cancel
      </button>
      {refused !== null && <p className="login-refused">{refused}</p>}
    </WayIn>
  );
}

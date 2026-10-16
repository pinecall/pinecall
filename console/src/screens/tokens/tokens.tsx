/** Tokens screen: personal keys and server tokens. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { dayAndTime } from "../../lib/format";
import { useScopes } from "../../lib/whoami";
import { useWorld } from "../../lib/world";
import { Button, Card, CardHead, Empty, Input, Page, PageHead, Pill, Refused, TableHead, TextAction } from "../../ui";
import { bunches, sorted, type Bunch } from "./bunches";
import { makeToken, readTokens, revokeToken, type Issued, type Listed } from "./door";
import "./tokens.css";

const SERVERS = "minmax(0,1.3fr) 96px minmax(0,1fr) 150px 140px";
const MINE = "minmax(0,1.3fr) minmax(0,1fr) 150px 140px";

/**
 * Personal keys are per device and follow the person's role. Server tokens belong to the org and
 * open only this console's world (`POST /v1/keys` refuses the other). A new token is shown once.
 */
export function Tokens(): ReactNode {
  const credentials = useCredentials();
  const { world } = useWorld();
  const scopes = useScopes();
  const [rows, setRows] = useState<Listed[] | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<Issued | null>(null);
  const [copied, setCopied] = useState(false);
  const [showRevoked, setShowRevoked] = useState(false);
  const [showMine, setShowMine] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  // Server tokens need the `app` scope; the gateway enforces it, the form just hides the option.
  const makes = scopes !== null && scopes.includes("app");

  const reread = async (): Promise<void> => setRows(await readTokens(credentials));

  useEffect(() => {
    let gone = false;
    readTokens(credentials).then(
      (kept) => {
        if (!gone) setRows(kept);
      },
      (failed: unknown) => {
        if (!gone) setRefused(failed instanceof Error ? failed.message : String(failed));
      },
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const make = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (label.trim() === "") {
      setRefused("Say what the key is for: the server or job that will use it.");
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      setMade(await makeToken(credentials, { label: label.trim(), env: world }));
      setCopied(false);
      setLabel("");
      await reread();
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  const stop = async (fingerprint: string): Promise<void> => {
    setRefused(null);
    try {
      await revokeToken(credentials, fingerprint);
      await reread();
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    }
  };

  const copy = async (line: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(line);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Page tight>
      <PageHead
        title="API keys"
        ledeWidth={640}
        lede={`The keys your servers and tools use to connect to Pinecall. Make one for each server, so you can cut one off without touching the others.`}
      />

      {makes && (
        <Card pad>
          <form className="keys-form" onSubmit={(event) => void make(event)}>
            <div className="keys-label-field">
              <label className="ui-label" htmlFor="token-label">
                New API key
              </label>
              <Input id="token-label" value={label} placeholder="What it is for, e.g. production server" onChange={(event) => setLabel(event.target.value)} />
            </div>
            <Button type="submit" kind="primary" size="form" disabled={busy}>
              {busy ? "Making…" : "Create"}
            </Button>
            <div className="keys-form-note">
              It works in {world} only, and can run your agent there and publish its knowledge base, nothing else.
              {world === "sandbox" ? " Production keys are made on the production console." : " Sandbox keys are made on the sandbox console."}
            </div>
          </form>
        </Card>
      )}

      {made !== null && (
        <Card>
          <CardHead
            title={`${made.label ?? "New API key"} · ${made.env}`}
            meta="shown once"
            action={
              <span className="keys-minted-actions">
                <Button size="xs" onClick={() => void copy(`PINECALL_KEY=${made.key}`)}>
                  {copied ? "Copied" : "Copy"}
                </Button>
                <Button size="xs" onClick={() => setMade(null)}>
                  Done
                </Button>
              </span>
            }
          />
          <pre className="ui-code">PINECALL_KEY={made.key}</pre>
          <div className="keys-minted-warn">Copy it now and put it in your server's secrets. Pinecall cannot show it again.</div>
        </Card>
      )}

      <Refused>{refused}</Refused>

      {rows !== null && (
        <Listing rows={rows} world={world} showRevoked={showRevoked} onShowRevoked={setShowRevoked} showMine={showMine} onShowMine={setShowMine} stop={stop} />
      )}
    </Page>
  );
}

/** The three lists: servers, the person's own keys by device, and the revoked behind a switch. */
function Listing({
  rows,
  world,
  showRevoked,
  onShowRevoked,
  showMine,
  onShowMine,
  stop,
}: {
  rows: Listed[];
  world: string;
  showRevoked: boolean;
  onShowRevoked: (shown: boolean) => void;
  showMine: boolean;
  onShowMine: (shown: boolean) => void;
  stop: (fingerprint: string) => Promise<void>;
}): ReactNode {
  const { servers, mine, revoked } = sorted(rows);
  return (
    <>
      <Card>
        <CardHead title="API keys" meta={`${servers.length} active in ${world}`} />
        {servers.length === 0 ? (
          <Empty>No API key yet. Make one above and give it to the server that runs your agent.</Empty>
        ) : (
          <>
            <TableHead columns={SERVERS} labels={["Key", "World", "Made by", "Last used", "Status>"]} />
            {servers.map((row) => (
              <Row key={row.fingerprint} row={row} columns={SERVERS} stop={stop} />
            ))}
          </>
        )}
      </Card>

      <Card>
        <CardHead
          title="Your sign-ins"
          meta={`${mine.reduce((all, bunch) => all + bunch.rows.length, 0)} browsers and computers signed in to your account`}
          action={<TextAction onClick={() => onShowMine(!showMine)}>{showMine ? "Hide" : "Show"}</TextAction>}
        />
        {!showMine ? null : mine.length === 0 ? (
          <Empty>Nothing is signed in with your account.</Empty>
        ) : (
          <>
            <TableHead columns={MINE} labels={["Signed in on", "Who", "Last used", "Status>"]} />
            {mine.map((bunch) => (
              <BunchRows key={`${bunch.label}:${bunch.rows[0]?.name ?? ""}`} bunch={bunch} stop={stop} />
            ))}
          </>
        )}
      </Card>

      {revoked.length > 0 && (
        <Card>
          <CardHead
            title="Revoked"
            meta={`${revoked.length} stopped working`}
            action={<TextAction onClick={() => onShowRevoked(!showRevoked)}>{showRevoked ? "Hide" : "Show"}</TextAction>}
          />
          {showRevoked &&
            bunches(revoked).flatMap((bunch) => bunch.rows).map((row) => <Row key={row.fingerprint} row={row} columns={row.kind === "server" ? SERVERS : MINE} stop={stop} />)}
        </Card>
      )}
    </>
  );
}

/** Keys of one label and person: a single one is a row; many are one line saying how many, opened to see each. */
function BunchRows({ bunch, stop }: { bunch: Bunch; stop: (fingerprint: string) => Promise<void> }): ReactNode {
  const [open, setOpen] = useState(false);
  const [only] = bunch.rows;
  if (bunch.rows.length === 1 && only !== undefined) return <Row row={only} columns={MINE} stop={stop} />;
  return (
    <>
      <div className="ui-table-row keys-row" style={{ gridTemplateColumns: MINE }}>
        <span className="keys-name">
          {bunch.label} <span className="ui-cell-faint">× {bunch.rows.length}</span>
        </span>
        <span className="ui-cell-ink ui-clip">{only?.name ?? "a person"}</span>
        <span className="ui-cell-faint">{bunch.lastUsed === null ? "never" : dayAndTime(bunch.lastUsed / 1000)}</span>
        <span className="ui-cell-end">
          <TextAction onClick={() => setOpen(!open)}>{open ? "Hide them" : "Show them"}</TextAction>
        </span>
      </div>
      {open && bunch.rows.map((row) => <Row key={row.fingerprint} row={row} columns={MINE} stop={stop} />)}
    </>
  );
}

/** A token row: label, world, owner, last use. */
function Row({ row, columns, stop }: { row: Listed; columns: string; stop: (fingerprint: string) => Promise<void> }): ReactNode {
  const [sure, setSure] = useState(false);
  const revoked = row.revoked_at !== null;
  const person = row.kind === "person";
  const whose = person ? (row.name ?? "a person") : (row.created_by ?? "the org");
  return (
    <div className="ui-table-row keys-row" style={{ gridTemplateColumns: columns }} onMouseLeave={() => setSure(false)}>
      <span className={revoked ? "keys-name keys-name-gone" : "keys-name"} title={row.fingerprint}>
        {row.label ?? row.fingerprint.slice(0, 12)}
      </span>
      {!person && <span className="ui-cell-faint">{row.env ?? "—"}</span>}
      <span className="ui-cell-ink ui-clip">{whose}</span>
      <span className="ui-cell-faint">{row.last_used_at === null ? "never" : dayAndTime(Date.parse(row.last_used_at) / 1000)}</span>
      <span className="ui-cell-end">
        {!revoked && (
          <span className={sure ? "keys-revoke keys-revoke-sure" : "keys-revoke"}>
            <TextAction danger onClick={() => (sure ? void stop(row.fingerprint) : setSure(true))}>
              {sure ? "Revoke it" : "Revoke"}
            </TextAction>
          </span>
        )}
        {revoked ? <Pill tone="gray">revoked</Pill> : <Pill tone="green">active</Pill>}
      </span>
    </div>
  );
}

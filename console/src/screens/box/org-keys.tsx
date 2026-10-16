/** An org's keys, as the box reads them: one issued for a machine and shown once, any of them stopped. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { scopesLine } from "@pinecall/core/scopes";
import { Button, Card, CardHead, Empty, Field, Input, Pill, Refused, Select, SelectItem, TableHead, TableRow, TextAction } from "../../ui";
import { issueKey, readKeys, revokeKey, type Issued } from "./door";
import { useDoor, useMove } from "./use-door";

const COLUMNS = "minmax(0,1fr) 96px 140px minmax(0,1.3fr) 92px";

// What a deployment runs on holds the app socket and nothing else; an org's own machine key holds
// every door. `null` is how the door is told "every scope".
const HOLDS: readonly { name: string; scopes: string[] | null }[] = [
  { name: "app — what a deployed agent runs on", scopes: ["app"] },
  { name: "everything — the org's own machine key", scopes: null },
];

export function OrgKeys({ named }: { named: string }): ReactNode {
  const credentials = useCredentials();
  const keys = useDoor(useCallback(() => readKeys(credentials, named), [credentials, named]));
  const acting = useMove();
  const [issuing, setIssuing] = useState(false);
  const [label, setLabel] = useState("");
  const [env, setEnv] = useState("production");
  const [holds, setHolds] = useState(0);
  const [minted, setMinted] = useState<Issued | null>(null);
  const [copied, setCopied] = useState(false);

  const issue = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const made = await acting.move(async () => {
      setMinted(await issueKey(credentials, named, { label: label.trim(), env, scopes: HOLDS[holds]?.scopes ?? null }));
      setCopied(false);
      await keys.reread();
    });
    if (made) {
      setLabel("");
      setIssuing(false);
    }
  };

  const live = (keys.value ?? []).filter((one) => one.revoked_at === null || one.revoked_at === undefined).length;

  return (
    <>
      {minted !== null && (
        <Card>
          <CardHead title={`The key for ${minted.label ?? "this machine"}`} meta="copy it now: the table keeps its sha256, and it is never shown again">
            <span className="box-head-moves">
              <Button size="xs" onClick={() => void navigator.clipboard.writeText(minted.key).then(() => setCopied(true))}>
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button size="xs" onClick={() => setMinted(null)}>
                Done
              </Button>
            </span>
          </CardHead>
          <pre className="ui-code">{minted.key}</pre>
        </Card>
      )}

      <Refused>{keys.refused ?? acting.refused}</Refused>

      {keys.value !== undefined && (
        <Card>
          <CardHead
            title="Keys"
            meta={`${live} live`}
            action={
              issuing ? undefined : (
                <Button kind="primary" size="sm" className="ui-card-action" onClick={() => setIssuing(true)}>
                  Issue a key
                </Button>
              )
            }
          />
          {issuing && (
            <div className="box-inline">
              <form className="ui-form" onSubmit={(event) => void issue(event)}>
                <Field label="What it is for" grow minWidth={200}>
                  <Input value={label} placeholder="prod server" onChange={(event) => setLabel(event.target.value)} required autoFocus />
                </Field>
                <Field label="World" minWidth={130}>
                  <Select value={env} onValueChange={(value) => setEnv(value)}>
                    <SelectItem value="production">production</SelectItem>
                    <SelectItem value="sandbox">sandbox</SelectItem>
                  </Select>
                </Field>
                <Field label="Opens" minWidth={260}>
                  <Select value={String(holds)} onValueChange={(value) => setHolds(Number(value))}>
                    {HOLDS.map((one, index) => (
                      <SelectItem key={one.name} value={String(index)}>
                        {one.name}
                      </SelectItem>
                    ))}
                  </Select>
                </Field>
                <Button kind="primary" size="form" type="submit" disabled={acting.busy || label.trim() === ""}>
                  {acting.busy ? "Issuing…" : "Issue"}
                </Button>
              </form>
              <div className="box-inline-foot">
                A machine's key names nobody: people get theirs by signing in.
                <span className="box-inline-close">
                  <TextAction onClick={() => setIssuing(false)}>Close</TextAction>
                </span>
              </div>
            </div>
          )}
          {keys.value.length === 0 ? (
            <Empty>No key issued to this org yet.</Empty>
          ) : (
            <>
              <TableHead columns={COLUMNS} labels={["Key", "World", "Whose", "Can do", ""]} />
              {keys.value.map((key) => {
                const gone = key.revoked_at !== null && key.revoked_at !== undefined;
                return (
                  <TableRow key={key.fingerprint} columns={COLUMNS}>
                    <span className={gone ? "ui-cell-faint ui-clip" : "ui-cell-strong ui-clip"} title={key.fingerprint}>
                      {key.label ?? key.fingerprint.slice(0, 12)}
                    </span>
                    <span>
                      {key.env === null || key.env === undefined ? <span className="ui-cell-faint">both</span> : <Pill tone={key.env === "production" ? "green" : "indigo"}>{key.env}</Pill>}
                    </span>
                    <span className="ui-cell-ink ui-clip">{key.name ?? "a machine"}</span>
                    <span className="ui-cell-faint ui-clip" title={key.scopes.join(", ")}>
                      {scopesLine(key.scopes)}
                    </span>
                    <span className="ui-cell-end">
                      {gone ? (
                        <span className="ui-cell-faint">revoked</span>
                      ) : (
                        <TextAction
                          danger
                          disabled={acting.busy}
                          onClick={() =>
                            void acting.move(async () => {
                              await revokeKey(credentials, key.fingerprint);
                              await keys.reread();
                            })
                          }
                        >
                          Revoke
                        </TextAction>
                      )}
                    </span>
                  </TableRow>
                );
              })}
            </>
          )}
        </Card>
      )}
    </>
  );
}

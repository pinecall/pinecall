/** An org's overview: contents, sign-in, agent import, and deletion. */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { Button, Card, CardHead, Field, Input, KV, Pill, Refused, Stat, Stats, TextAction } from "../../ui";
import { moveAgent, readSso, removeOrg, requireSso, type OneOrg } from "./door";
import { useDoor, useMove } from "./use-door";

export function OrgOverview({ org }: { org: OneOrg }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const sso = useDoor(useCallback(() => readSso(credentials, org.slug), [credentials, org.slug]));
  const acting = useMove();
  const [agent, setAgent] = useState("");
  const [moved, setMoved] = useState<string | null>(null);
  const [sure, setSure] = useState(false);

  const bring = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setMoved(null);
    await acting.move(async () => {
      const answered = await moveAgent(credentials, org.slug, agent.trim());
      setMoved(`${agent.trim()} is ${org.slug}'s now: ${answered.logs} ${answered.logs === 1 ? "log" : "logs"}${answered.numbers.length > 0 ? `, and ${answered.numbers.join(", ")}` : ""}.`);
      setAgent("");
    });
  };

  const of = (limit: number | null | undefined): string | undefined => (limit === null || limit === undefined ? undefined : `of ${limit}`);

  return (
    <>
      <Stats min={170}>
        <Stat size="small" label="Seats" value={org.holding.seats} of={of(org.quotas["production"]?.limits["seats"])} />
        <Stat size="small" label="Numbers bought" value={org.holding.numbers} of={of(org.quotas["production"]?.limits["numbers"])} />
        <Stat size="small" label="Memory facts" value={org.holding.memory_facts} of={of(org.quotas["production"]?.limits["memory_facts"])} />
        <Stat size="small" label="Knowledge chunks" value={org.holding.knowledge_chunks} of={of(org.quotas["production"]?.limits["knowledge_chunks"])} />
      </Stats>

      <Refused>{acting.refused}</Refused>

      <Card>
        <CardHead title="Sign-in" meta="how this org's people prove who they are" />
        <div className="box-kvs">
          <KV label="Provider" keyWidth={120}>
            {sso.value?.configured ? (sso.value.issuer ?? "its own identity provider") : "passwords — no identity provider wired"}
          </KV>
          {sso.value?.configured && (
            <KV label="Passwords" keyWidth={120}>
              {sso.value.required ? (
                <span className="box-line">
                  <Pill tone="amber">stopped</Pill>
                  <TextAction disabled={acting.busy} onClick={() => void acting.move(async () => { await requireSso(credentials, org.slug, false); await sso.reread(); })}>
                    Let passwords work again
                  </TextAction>
                </span>
              ) : (
                "still work"
              )}
            </KV>
          )}
        </div>
        {sso.value?.configured && sso.value.required && (
          <div className="ui-card-foot">The break-glass: the day their provider stops answering, the admin who would turn this off is the one locked out.</div>
        )}
      </Card>

      <Card>
        <CardHead title="Bring an agent here" meta="one that registered in the wrong org, with every call it took and its numbers" />
        <div className="ui-card-body">
          <form className="ui-form" onSubmit={(event) => void bring(event)}>
            <Field label="Agent slug" grow minWidth={220}>
              <Input value={agent} placeholder="clinica-norte" onChange={(event) => setAgent(event.target.value)} required />
            </Field>
            <Button size="form" type="submit" disabled={acting.busy || agent.trim() === ""}>
              Move it here
            </Button>
          </form>
          {moved !== null && <div className="box-done box-done-under">{moved}</div>}
          <div className="ui-note box-note">The agent must be stopped first: a slug somebody is holding is refused.</div>
        </div>
      </Card>

      <Card>
        <CardHead title="Remove this organization" meta="refused while a live key or a route still names it" />
        <div className="ui-card-body box-line">
          {sure ? (
            <>
              <span className="ui-note">Forget {org.slug} for good?</span>
              <Button
                kind="danger"
                size="sm"
                disabled={acting.busy}
                onClick={() =>
                  void acting.move(async () => {
                    await removeOrg(credentials, org.slug);
                    void navigate("/box/orgs");
                  })
                }
              >
                Yes, remove it
              </Button>
              <TextAction onClick={() => setSure(false)}>Cancel</TextAction>
            </>
          ) : (
            <Button kind="danger" size="sm" onClick={() => setSure(true)}>
              Remove {org.slug}
            </Button>
          )}
        </div>
      </Card>
    </>
  );
}

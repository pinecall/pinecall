/** The editor's Data collection: the fields the agent gathers from the caller, when the call ends, and where the results are sent. */

import type { ReactNode } from "react";

import { Check, Field, Input, Switch } from "../../ui";
import type { Collect } from "./door";
import { aCollect } from "./draft";
import { HeaderRows, ParamRows } from "./rows";
import { Section } from "./section";

export function Collection({ collect, secrets, onChange }: { collect: Collect | null | undefined; secrets: readonly string[]; onChange: (collect: Collect | null) => void }): ReactNode {
  const on = collect !== null && collect !== undefined;
  return (
    <Section
      title="Data collection"
      meta="what the agent gathers from the caller"
      action={<Switch on={on} label="Collect data" onChange={(now) => onChange(now ? aCollect() : null)} />}
    >
      {!on ? (
        <p className="sto-hint">Off. Switched on, the agent asks for the fields below during the call and keeps what the caller answers.</p>
      ) : (
        <>
          <div className="sto-label">Fields</div>
          <ParamRows params={collect.fields} adding="Add a field" onChange={(fields) => onChange({ ...collect, fields })} />
          <Check checked={collect.end_when_done} onChange={(end_when_done) => onChange({ ...collect, end_when_done })}>
            End the call once the required fields are in
          </Check>
          <Field label="Then, the agent is told">
            <Input value={collect.closing} onChange={(event) => onChange({ ...collect, closing: event.target.value })} />
          </Field>
          <Field label="Send the results to (optional)">
            <Input
              value={collect.send_to ?? ""}
              placeholder="https://api.example.com/leads"
              spellCheck={false}
              onChange={(event) => onChange({ ...collect, send_to: event.target.value === "" ? null : event.target.value })}
            />
          </Field>
          <p className="sto-hint">When the call ends, the fields and the transcript are posted there as JSON. Left empty, they are only kept with the call.</p>
          {(collect.send_to ?? "") !== "" && (
            <>
              <div className="sto-label">Headers of that request</div>
              <HeaderRows headers={collect.headers} secrets={secrets} onChange={(headers) => onChange({ ...collect, headers })} />
            </>
          )}
        </>
      )}
    </Section>
  );
}

/** The secrets every deployed app starts with, in this world: listed by name, set and forgotten, never read back. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { ago } from "../lib/format";
import { ConfirmButton } from "./confirm";
import { dropSecret, putSecret, readSecrets, whoIs, type Secret } from "./door";

const A_NAME = /^[A-Z][A-Z0-9_]*$/;

function nameRefused(name: string): string | null {
  if (!A_NAME.test(name)) return "A name is an environment variable's: capitals, digits and underscores, starting with a capital.";
  if (name.startsWith("PINECALL_")) return "A name starting with PINECALL_ is the box's own.";
  return null;
}

export function Secrets({ names }: { names: ReadonlyMap<string, string> }): ReactNode {
  const credentials = useCredentials();
  const [secrets, setSecrets] = useState<Secret[] | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readSecrets(credentials).then(
      (read) => !gone && setSecrets(read),
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  const save = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const named = name.trim();
    const wrong = nameRefused(named) ?? (value === "" ? "A secret needs a value." : null);
    if (wrong !== null) return setRefused(wrong);
    setRefused(null);
    try {
      setSecrets(await putSecret(credentials, named, value));
      setName("");
      setValue("");
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  const forget = async (one: string): Promise<void> => {
    setRefused(null);
    try {
      setSecrets(await dropSecret(credentials, one));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  };

  return (
    <section className="dash-card" aria-label="Secrets">
      <div className="dash-card-top">
        <span className="dash-eyebrow">Secrets</span>
        <span className="dash-quiet">Every deployed app in this world</span>
      </div>
      {refused !== null && <p className="app-refused">{refused}</p>}
      {secrets !== null && secrets.length > 0 && (
        <div className="dash-rows app-secrets">
          {secrets.map((one) => (
            <div key={one.name} className="app-secret dash-row">
              <code className="app-secret-name dash-clip">{one.name}</code>
              <span className="dash-quiet dash-clip">
                {whoIs(names, one.set_by)}, {ago(one.set_at)}
              </span>
              <ConfirmButton label="Forget" asks="Sure?" danger onConfirm={() => void forget(one.name)} />
            </div>
          ))}
        </div>
      )}
      {secrets !== null && secrets.length === 0 && <p className="dash-quiet app-none">No secret yet. Add what your apps read from the environment.</p>}
      <form className="app-secret-form" onSubmit={(event) => void save(event)}>
        <input className="app-input" aria-label="Name" placeholder="CRM_TOKEN" autoComplete="off" spellCheck={false} value={name} onChange={(event) => setName(event.target.value)} />
        <input className="app-input" aria-label="Value" placeholder="Value" type="password" autoComplete="new-password" value={value} onChange={(event) => setValue(event.target.value)} />
        <button type="submit" className="app-button">
          Add
        </button>
      </form>
    </section>
  );
}

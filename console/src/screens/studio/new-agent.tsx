/** The New agent form, on Studio and on the Agents screen: a name, an agent made in Studio, and Studio opened on it once the gateway holds it. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../../lib/org";
import { Button, Card, Field, Input, Refused } from "../../ui";
import { makeStudioAgent } from "./door";

const A_SLUG = /^[a-z][a-z0-9-]*$/;
const LONGEST = 40;

/** Why a name would be refused, before the gateway is asked; null when it would not be. */
function nameRefused(name: string): string | null {
  if (name.length > LONGEST) return `A name is at most ${LONGEST} characters.`;
  if (!A_SLUG.test(name)) return "A name is lowercase letters, digits and dashes, starting with a letter.";
  return null;
}

const studioOf = (slug: string): string => `/a/${encodeURIComponent(slug)}/studio`;

export function NewAgent({ onCancel }: { onCancel: () => void }): ReactNode {
  const credentials = useCredentials();
  const { agents } = useOrg();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [made, setMade] = useState<string | null>(null);

  // The shell shows an agent's screens only for one the gateway holds, and the gateway holds a new
  // one a moment after making it: the org's feed says when, and the list it re-reads then opens Studio.
  useEffect(() => {
    if (made !== null && agents.some((one) => one.slug === made)) navigate(studioOf(made));
  }, [made, agents, navigate]);

  const make = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const slug = name.trim();
    const wrong = nameRefused(slug);
    if (wrong !== null) {
      setRefused(wrong);
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      await makeStudioAgent(credentials, slug);
      setMade(slug);
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card pad>
      <form className="ui-form" onSubmit={(event) => void make(event)}>
        <Field label="Name of the new agent" grow minWidth={240}>
          <Input value={name} placeholder="front-desk" autoComplete="off" spellCheck={false} maxLength={LONGEST} disabled={made !== null} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Button kind="primary" size="form" type="submit" disabled={busy || made !== null || name.trim() === ""}>
          {busy ? "Making…" : "Make it"}
        </Button>
        <Button size="form" onClick={onCancel}>
          Cancel
        </Button>
      </form>
      <p className="ui-note">
        {made === null ? (
          "Built in Studio, with no code: lowercase letters, digits and dashes, starting with a letter. It starts in the sandbox; Studio deploys it to production."
        ) : (
          <>
            Made {made}. Studio opens on it as soon as the gateway holds it — <Link to={studioOf(made)}>open it now</Link>.
          </>
        )}
      </p>
      <Refused>{refused}</Refused>
    </Card>
  );
}

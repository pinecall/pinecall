/** The New agent dialog, on Studio and on the Agents screen: a name, an agent made in Studio, and Studio opened on it once the gateway holds it. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useOrg } from "../../lib/org";
import { Button, Icon, Input } from "../../ui";
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

  // Escape or a click outside closes it, until the agent is being made.
  const settled = !busy && made === null;
  useEffect(() => {
    if (!settled) return;
    const escape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [settled, onCancel]);

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
    <div className="sto-new-veil" onMouseDown={() => settled && onCancel()}>
      <form
        className="sto-new"
        role="dialog"
        aria-modal
        aria-labelledby="sto-new-title"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={(event) => void make(event)}
      >
        <div className="sto-new-head">
          <span className="sto-new-mark" aria-hidden>
            <Icon name="bot" size={20} />
          </span>
          <span className="sto-new-words">
            <span id="sto-new-title" className="sto-new-title">
              New agent
            </span>
            <span className="sto-new-said">Built in Studio, with no code. It answers in the sandbox until you deploy it.</span>
          </span>
        </div>

        <label className="sto-new-field">
          <span className="ui-label">Name</span>
          <Input
            size="lg"
            value={name}
            placeholder="front-desk"
            autoFocus
            autoComplete="off"
            spellCheck={false}
            maxLength={LONGEST}
            disabled={made !== null}
            aria-invalid={refused !== null}
            onChange={(event) => {
              setName(event.target.value);
              setRefused(null);
            }}
          />
          {refused !== null ? (
            <span className="sto-new-hint sto-new-wrong">{refused}</span>
          ) : made !== null ? (
            <span className="sto-new-hint">
              Made {made}. Studio opens on it in a moment — <Link to={studioOf(made)}>open it now</Link>.
            </span>
          ) : (
            <span className="sto-new-hint">Lowercase letters, digits and dashes, starting with a letter.</span>
          )}
        </label>

        <div className="sto-new-foot">
          <Button size="form" onClick={onCancel} disabled={!settled}>
            Cancel
          </Button>
          <Button kind="primary" size="form" type="submit" disabled={!settled || name.trim() === ""}>
            {made !== null ? "Opening Studio…" : busy ? "Creating…" : "Create agent"}
          </Button>
        </div>
      </form>
    </div>
  );
}

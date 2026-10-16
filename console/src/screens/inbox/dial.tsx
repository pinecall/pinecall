/** Placing a call from the inbox: whether the org can, the confirm before a call back, and a number dialled by hand. */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { GatewayError } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { prettyNumber } from "@pinecall/core/calls";
import { Button, Field, Input, Select, SelectItem } from "../../ui";
import { dial, readOutbound, type Outbound } from "../numbers/door";
import "./dial.css";

// E.164, as the gateway's first guard reads it.
const E164 = /^\+[1-9]\d{4,14}$/;

/**
 * Whether this org can dial out, read once per screen. Null until it can: a gateway without the
 * door, a key that may not ask, a trunk nobody provisioned — each is simply no button, never an error.
 */
export function useOutbound(): Outbound | null {
  const credentials = useCredentials();
  const [outbound, setOutbound] = useState<Outbound | null>(null);
  useEffect(() => {
    let gone = false;
    readOutbound(credentials).then(
      (read) => {
        if (!gone) setOutbound(read !== null && read.ready ? read : null);
      },
      () => undefined,
    );
    return () => {
      gone = true;
    };
  }, [credentials]);
  return outbound;
}

/** Which of the org's numbers the call is placed from; nothing to choose with one. */
function From({ outbound, value, onChange }: { outbound: Outbound; value: string; onChange: (from: string) => void }): ReactNode {
  if (outbound.from_numbers.length < 2) return null;
  return (
    <Field label="From">
      <Select size="sm" value={value} onValueChange={(value) => onChange(value)}>
        <SelectItem value="">the agent's own number</SelectItem>
        {outbound.from_numbers.map((one) => (
          <SelectItem key={one} value={one}>
            {prettyNumber(one)}
          </SelectItem>
        ))}
      </Select>
    </Field>
  );
}

/** The confirm under "Call back": who, as whom, from where — and the call it becomes opens as a conversation. */
export function CallBack({
  agent,
  to,
  outbound,
  onClose,
  onRefused,
}: {
  agent: string;
  to: string;
  outbound: Outbound;
  onClose: () => void;
  onRefused: (sentence: string) => void;
}): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [from, setFrom] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // Out of the way on Escape, or a click anywhere but the button that opened it (its own toggle).
  useEffect(() => {
    const escape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    const away = (event: MouseEvent): void => {
      const anchor = box.current?.parentElement;
      if (anchor !== null && anchor !== undefined && !anchor.contains(event.target as Node)) onClose();
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("mousedown", away);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("mousedown", away);
    };
  }, [onClose]);

  const call = async (): Promise<void> => {
    setBusy(true);
    try {
      const placed = await dial(credentials, agent, to, from);
      void navigate(`/calls/${placed}`);
    } catch (failed) {
      // The guard's own sentence, where the thread says what it refused.
      onRefused(failed instanceof GatewayError ? failed.message : String(failed));
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dial-pop" role="dialog" aria-label="call back" ref={box}>
      <div className="dial-ask">
        Call {prettyNumber(to)} as {agent}?
      </div>
      <From outbound={outbound} value={from} onChange={setFrom} />
      <div className="dial-moves">
        <Button kind="primary" size="md" disabled={busy} onClick={() => void call()}>
          {busy ? "Calling…" : "Call"}
        </Button>
        <Button size="md" disabled={busy} onClick={onClose}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** A number typed by hand, in the panel the round + opens. The gateway's guards decide whether it may be called. */
export function DialForm({ agent, outbound, onClose }: { agent: string; outbound: Outbound; onClose: () => void }): ReactNode {
  const credentials = useCredentials();
  const navigate = useNavigate();
  const [to, setTo] = useState("");
  const [from, setFrom] = useState("");
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const number = to.replace(/[\s()-]/g, "");

  const call = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!E164.test(number)) {
      setRefused("A number is written whole, with its country: +14176743169.");
      return;
    }
    setBusy(true);
    setRefused(null);
    try {
      const placed = await dial(credentials, agent, number, from);
      onClose();
      void navigate(`/calls/${placed}`);
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="dial-form" onSubmit={(event) => void call(event)}>
      <Field label="Number">
        <Input size="sm" value={to} placeholder="+1 417 674 3169" autoFocus autoComplete="off" onChange={(event) => setTo(event.target.value)} />
      </Field>
      <From outbound={outbound} value={from} onChange={setFrom} />
      <p className="dial-note">
        {outbound.guards.dial_anywhere
          ? `${agent} places the call and speaks first.`
          : `${agent} places the call and speaks first. Only a number that has already called or written to you is dialled.`}
      </p>
      {refused !== null && <p className="dial-refused">{refused}</p>}
      <Button kind="primary" size="md" type="submit" disabled={busy || number === ""}>
        {busy ? "Calling…" : "Call"}
      </Button>
    </form>
  );
}

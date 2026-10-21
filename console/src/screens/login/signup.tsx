/** Sign-up: the org and its admin, then six digits mailed — shown only where the gateway opens sign-ups. */

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { GatewayError } from "@pinecall/core/api";
import { signUp } from "@pinecall/core/signup";
import { discovered, type Discovered } from "@pinecall/core/the-floor";
import { DEVICE } from "../../lib/device";
import { inTheWorld, WORLD, WORLD_BASE } from "../../lib/mode";
import { useTurnstile } from "./turnstile";
import { WayIn } from "./way-in";

/** Where the mailed code is typed, under this world's base; the address rides the query. */
export const VERIFY = "/signup/verify";

/**
 * Every self-hosted runtime serves this page, so whether it takes sign-ups is the gateway's word
 * (`/.well-known/pinecall`), never the page's: closed, the page says so and the door refuses anyway.
 */
export function SignUp({ base }: { base: string }): ReactNode {
  const [floor, setFloor] = useState<Discovered | null>(null);
  useEffect(() => {
    let gone = false;
    void discovered(base).then((said) => {
      if (!gone) setFloor(said);
    });
    return () => {
      gone = true;
    };
  }, [base]);

  if (floor === null) return <WayIn title="Create an account" />;
  if (!floor.signup) {
    return (
      <WayIn
        title="Sign-ups are closed here"
        lede="This Pinecall takes no sign-ups: whoever runs it makes the org and invites you."
        aside={
          <>
            Already invited? <a href={WORLD_BASE}>Sign in</a>
          </>
        }
      />
    );
  }
  return <TheForm base={base} floor={floor} />;
}

function TheForm({ base, floor }: { base: string; floor: Discovered }): ReactNode {
  const [name, setName] = useState("");
  const [person, setPerson] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const captcha = useTurnstile(floor.turnstile, "signup");

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRefused(null);
    try {
      const mailed = await signUp(base, { name: name.trim(), person: person.trim(), email: email.trim(), password }, DEVICE, captcha.spend());
      window.location.assign(inTheWorld(WORLD, `${VERIFY}?email=${encodeURIComponent(mailed.email)}`));
    } catch (failed) {
      setRefused(failed instanceof GatewayError ? failed.message : String(failed));
      setBusy(false);
    }
  };

  return (
    <WayIn
      title="Create an account"
      lede="Your own org on this Pinecall: its agents, the console and the log of every call."
      aside={
        <>
          Already have an account? <a href={WORLD_BASE}>Sign in</a>
        </>
      }
    >
      <form onSubmit={(event) => void submit(event)}>
        <label className="login-label" htmlFor="signup-name">
          Company
        </label>
        <input id="signup-name" className="login-input" value={name} onChange={(event) => setName(event.target.value)} autoComplete="organization" maxLength={120} autoFocus required />

        <label className="login-label" htmlFor="signup-person">
          Your name
        </label>
        <input id="signup-person" className="login-input" value={person} onChange={(event) => setPerson(event.target.value)} autoComplete="name" maxLength={120} required />

        <label className="login-label" htmlFor="signup-email">
          Work email
        </label>
        <input id="signup-email" className="login-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" maxLength={200} required />

        <div className="login-label-row">
          <label className="login-label" htmlFor="signup-password">
            Password
          </label>
          {floor.min_password > 0 && <span className="login-hint">{floor.min_password} characters at least</span>}
        </div>
        <div className="login-secret">
          <input
            id="signup-password"
            className="login-input"
            type={shown ? "text" : "password"}
            value={password}
            minLength={floor.min_password > 0 ? floor.min_password : undefined}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            maxLength={200}
            required
          />
          <button type="button" className="login-eye" aria-label={shown ? "Hide password" : "Show password"} aria-pressed={shown} onClick={() => setShown(!shown)}>
            {shown ? "hide" : "show"}
          </button>
        </div>

        {captcha.widget}

        <button className="login-go" type="submit" disabled={busy || !captcha.ready}>
          {busy ? "Creating your account…" : "Create account"}
        </button>

        {refused !== null && <p className="login-refused">{refused}</p>}
      </form>
    </WayIn>
  );
}

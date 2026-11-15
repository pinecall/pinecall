/** User settings: who is signed in, the name and the password they change themselves, and the devices signed in as them. */

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { discovered } from "@pinecall/core/the-floor";
import { ConfirmButton } from "../apps/confirm";
import { revokeKey } from "../settings/door";
import { ago } from "../lib/format";
import { API_BASE, DEVICE } from "../lib/key";
import { useOrg } from "../lib/org";
import { Icon, type IconName } from "../shell/icons";
import { PageHead } from "../shell/page-head";
import { Field } from "../ui/setting";
import { changePassword, readMe, readSignIns, rename, signOutOthers, type Me, type SignIn } from "./door";
import "../dashboard/dashboard.css";
import "../configure/configure.css";
import "../test/test.css";
import "../settings/settings.css";
import "./account.css";

const at = (iso: string | null): number | null => (iso === null ? null : Date.parse(iso) / 1000);

function Card({ icon, title, about, tone, children }: { icon: IconName; title: string; about: string; tone: string; children: ReactNode }): ReactNode {
  return (
    <section className={`tst-list ${tone}`} aria-label={title}>
      <header className="tst-head">
        <span className="tst-head-mark" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
        <span className="tst-head-words">
          <span className="tst-head-title">{title}</span>
          <span className="tst-head-about">{about}</span>
        </span>
      </header>
      {children}
    </section>
  );
}

function Profile({ me, onRenamed }: { me: Me; onRenamed: (me: Me) => void }): ReactNode {
  const credentials = useCredentials();
  const { orgs } = useOrg();
  const [name, setName] = useState(me.name);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ refused: boolean; words: string } | null>(null);
  const here = orgs?.find((one) => one.here);
  const save = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setSaid(null);
    rename(credentials, name.trim()).then(
      (renamed) => (onRenamed(renamed), setName(renamed.name), setSaid({ refused: false, words: "Saved." })),
      (failed: unknown) => setSaid({ refused: true, words: saidBy(failed) }),
    ).finally(() => setBusy(false));
  };
  return (
    <Card icon="user" title="Profile" about="Who you are in this organization." tone="set-tone-accent">
      <form className="acc-form" onSubmit={save}>
        <Field label="Name">
          <input className="cfg-input" aria-label="Name" autoComplete="name" maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Email">
          <input className="cfg-input" aria-label="Email" readOnly value={me.email} />
        </Field>
        <Field label="Role">
          <input className="cfg-input" aria-label="Role" readOnly value={me.role} />
        </Field>
        <Field label="Organization">
          <input className="cfg-input" aria-label="Organization" readOnly value={here?.name ?? here?.slug ?? ""} />
        </Field>
        <div className="acc-foot">
          <button type="submit" className="cfg-save" disabled={busy || name.trim() === "" || name.trim() === me.name}>
            {busy ? "Saving…" : "Save"}
          </button>
          {said !== null && <span className={said.refused ? "cfg-refused" : "acc-done"}>{said.words}</span>}
        </div>
      </form>
    </Card>
  );
}

function Password({ me, onChanged }: { me: Me; onChanged: () => void }): ReactNode {
  const credentials = useCredentials();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [shortest, setShortest] = useState(0);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ refused: boolean; words: string } | null>(null);

  useEffect(() => {
    let gone = false;
    void discovered(API_BASE).then((floor) => !gone && setShortest(floor.min_password));
    return () => {
      gone = true;
    };
  }, []);

  if (!me.has_password) {
    return (
      <Card icon="lock" title="Password" about="What opens your account beside your provider." tone="set-tone-blue">
        <p className="acc-note">You have no password: you sign in with Google or your organization's provider. To set one, sign out and use “Forgot your password?” on the sign-in page; the link is mailed to {me.email}.</p>
      </Card>
    );
  }
  const differ = again !== "" && again !== password;
  const change = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setSaid(null);
    changePassword(credentials, current, password).then(
      () => (setCurrent(""), setPassword(""), setAgain(""), setSaid({ refused: false, words: "Password changed. Every other device signed in as you was signed out." }), onChanged()),
      (failed: unknown) => setSaid({ refused: true, words: saidBy(failed) }),
    ).finally(() => setBusy(false));
  };
  return (
    <Card icon="lock" title="Password" about="One password opens every organization you are in. Changing it signs out every other device." tone="set-tone-blue">
      <form className="acc-form" onSubmit={change}>
        <Field label="Current password">
          <input className="cfg-input" type="password" aria-label="Current password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} />
        </Field>
        <span />
        <Field label={shortest > 0 ? `New password, ${shortest} characters at least` : "New password"}>
          <input className="cfg-input" type="password" aria-label="New password" autoComplete="new-password" minLength={shortest > 0 ? shortest : undefined} value={password} onChange={(event) => setPassword(event.target.value)} />
        </Field>
        <Field label="New password, again">
          <input className="cfg-input" type="password" aria-label="New password, again" autoComplete="new-password" value={again} onChange={(event) => setAgain(event.target.value)} />
        </Field>
        <div className="acc-foot">
          <button type="submit" className="cfg-save" disabled={busy || current === "" || password.length < Math.max(shortest, 1) || again !== password}>
            {busy ? "Changing…" : "Change password"}
          </button>
          {differ && <span className="cfg-refused">The two do not match.</span>}
          {!differ && said !== null && <span className={said.refused ? "cfg-refused" : "acc-done"}>{said.words}</span>}
        </div>
      </form>
    </Card>
  );
}

/** The sign-ins one device name left, the latest used first. */
interface Device {
  name: string;
  signIns: SignIn[];
}

/** One row per device name, in the order of the list: the device used last comes first. */
function byDevice(signIns: readonly SignIn[]): Device[] {
  const devices = new Map<string, SignIn[]>();
  for (const one of signIns) {
    const name = one.label === null ? "A sign-in" : one.label === DEVICE ? "A browser" : one.label;
    devices.set(name, [...(devices.get(name) ?? []), one]);
  }
  return [...devices].map(([name, theirs]) => ({ name, signIns: theirs }));
}

const used = (one: SignIn): string => (one.last_used_at === null ? "Never used" : `Used ${ago(at(one.last_used_at))}`);

function SignInRow({ name, one, inner, onRevoke }: { name: string; one: SignIn; inner: boolean; onRevoke: (fingerprint: string) => void }): ReactNode {
  return (
    <div className={`tst-row set-row${inner ? " set-row-inner" : ""}`}>
      <span className="tst-row-words">
        <span className="tst-row-name">
          <span className="dash-clip">{name}</span>
          {one.current && <span className="tst-tag">This device</span>}
        </span>
        {!inner && <span className="tst-row-under dash-clip">Signed in {ago(at(one.created_at))}</span>}
      </span>
      <span className="tst-row-when">{used(one)}</span>
      {!one.current && <ConfirmButton label="Sign out" asks="Sign it out?" danger onConfirm={() => onRevoke(one.fingerprint)} />}
    </div>
  );
}

function DeviceRows({ device, onRevoke }: { device: Device; onRevoke: (fingerprint: string) => void }): ReactNode {
  const [latest] = device.signIns;
  if (latest === undefined) return null;
  if (device.signIns.length === 1) return <SignInRow name={device.name} one={latest} inner={false} onRevoke={onRevoke} />;
  return (
    <details className="acc-device">
      <summary className="tst-row set-row">
        <span className="tst-row-words">
          <span className="tst-row-name">
            <span className="dash-clip">{device.name}</span>
            {device.signIns.some((one) => one.current) && <span className="tst-tag">This device</span>}
          </span>
          <span className="tst-row-under dash-clip">Signed in {device.signIns.length} times</span>
        </span>
        <span className="tst-row-when">{used(latest)}</span>
        <span className="acc-fold" aria-hidden="true" />
      </summary>
      {device.signIns.map((one) => (
        <SignInRow key={one.fingerprint} name={`Signed in ${ago(at(one.created_at))}`} one={one} inner onRevoke={onRevoke} />
      ))}
    </details>
  );
}

function SignIns({ signIns, onRevoke, onRevokeOthers }: { signIns: readonly SignIn[] | null; onRevoke: (fingerprint: string) => void; onRevokeOthers: () => void }): ReactNode {
  const others = (signIns ?? []).filter((one) => !one.current).length;
  return (
    <Card icon="server" title="Where you are signed in" about="Each device signed in to this organization as you: a browser, the CLI, a phone. One that goes 30 days without being used is signed out by itself." tone="set-tone-good">
      {signIns === null && <p className="dash-quiet tst-none">Reading…</p>}
      {others > 0 && (
        <div className="acc-others">
          <span className="acc-note">
            {others === 1 ? "1 other sign-in" : `${others} other sign-ins`} besides this one.
          </span>
          <ConfirmButton label="Sign out everywhere else" asks="Sign them all out?" danger onConfirm={onRevokeOthers} />
        </div>
      )}
      {byDevice(signIns ?? []).map((device) => (
        <DeviceRows key={device.name} device={device} onRevoke={onRevoke} />
      ))}
    </Card>
  );
}

export function AccountPage(): ReactNode {
  const credentials = useCredentials();
  const { rereadWhose } = useOrg();
  const [me, setMe] = useState<Me | null>(null);
  const [signIns, setSignIns] = useState<SignIn[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const rereadSignIns = useCallback((): void => void readSignIns(credentials).then(setSignIns, (failed: unknown) => (setSignIns([]), setRefused(saidBy(failed)))), [credentials]);

  useEffect(() => {
    readMe(credentials).then(setMe, (failed: unknown) => setRefused(saidBy(failed)));
    rereadSignIns();
  }, [credentials, rereadSignIns]);

  const revoke = (fingerprint: string): void => {
    setRefused(null);
    revokeKey(credentials, fingerprint).then(rereadSignIns, (failed: unknown) => (setRefused(saidBy(failed)), rereadSignIns()));
  };
  const revokeOthers = (): void => {
    setRefused(null);
    signOutOthers(credentials).then(rereadSignIns, (failed: unknown) => (setRefused(saidBy(failed)), rereadSignIns()));
  };

  return (
    <>
      <PageHead />
      <div className="tst set">
        {refused !== null && (
          <p className="cfg-refused" role="alert">
            {refused}
          </p>
        )}
        {me !== null && (
          <>
            <Profile me={me} onRenamed={(renamed) => (setMe(renamed), rereadWhose())} />
            <Password me={me} onChanged={rereadSignIns} />
            <SignIns signIns={signIns} onRevoke={revoke} onRevokeOthers={revokeOthers} />
          </>
        )}
      </div>
    </>
  );
}

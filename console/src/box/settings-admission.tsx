/** Admission: what a new organization gets when it is made, in each environment: its limits, and the vendors it is lent. */

import { useCallback, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { EditDialog } from "../configure/dialog";
import { brandOf } from "../configure/vendors";
import { count } from "../lib/format";
import { useMove } from "../numbers/parts";
import { Mark } from "../ui/setting";
import { limitOf, QUOTAS, readAdmission, readHeldVendors, saveAdmission, SHAPES, WORLDS, type Admission, type Newborn, type Quota, type Shape, type World } from "./settings-door";
import { LendsPanel, lendSaid, modeOf } from "./settings-lends";
import { Effect, Refusal, Section, useDoor } from "./settings-parts";

type Whose = "first" | "later";

const WORLD_NAMES: Record<World, string> = { sandbox: "Sandbox", production: "Production" };

const ABOUT: Record<Quota | Shape, { name: string; about: string; unit: string }> = {
  minutes: { name: "Call minutes", about: "Minutes of spoken calls, each month.", unit: "a month" },
  messages: { name: "Chat messages", about: "Written turns, each month.", unit: "a month" },
  llm_tokens: { name: "Model tokens", about: "What its agents read and write, each month.", unit: "a month" },
  concurrent_calls: { name: "Calls at once", about: "Calls on the line at the same moment.", unit: "at once" },
  agents: { name: "Agents", about: "How many agents it may have.", unit: "" },
  numbers: { name: "Phone numbers", about: "Numbers bought through this deployment.", unit: "" },
  seats: { name: "People", about: "Members, invited or active.", unit: "" },
  hosted_apps: { name: "Hosted apps", about: "Apps and Studio agents this deployment runs for it.", unit: "" },
  memory_facts: { name: "Remembered facts", about: "What its agents remember about callers.", unit: "" },
  knowledge_chunks: { name: "Knowledge", about: "Pieces of text indexed from its documents.", unit: "pieces" },
  evals: { name: "Evaluations", about: "Judge verdicts on this deployment's keys, each month.", unit: "a month" },
  simulations: { name: "Simulated calls", about: "Test calls played by a pretend caller, each month.", unit: "a month" },
  budget_usd: { name: "Spend cap", about: "Dollars a month, both environments together.", unit: "USD a month" },
  simulations_at_once: { name: "Simulated calls at once", about: "Pretend callers on the line together.", unit: "at once" },
  comparison_calls: { name: "Calls in one comparison", about: "The most one comparison may place.", unit: "" },
};

function limitSaid(name: Quota | Shape, value: number | null, shape: boolean): string {
  if (value === null) return shape ? "The usual, 10" : "Unlimited";
  if (value === 0) return "None";
  return `${count(value)} ${ABOUT[name].unit}`.trim();
}

/** The environment's row with its limits typed again: an empty field is null, which is no limit. */
function withLimits(standing: Newborn | undefined, typed: Record<string, string>): Newborn {
  const limits = Object.fromEntries([...QUOTAS, ...SHAPES].map((name) => [name, typed[name] === undefined || typed[name] === "" ? null : Number(typed[name])]));
  return { ...(standing ?? {}), ...limits };
}

function LimitsPanel({ whom, standing, saving, refused, onSave, onClose }: { whom: string; standing: Newborn | undefined; saving: boolean; refused: string | null; onSave: (row: Newborn) => void; onClose: () => void }): ReactNode {
  const [typed, setTyped] = useState<Record<string, string>>(() => Object.fromEntries([...QUOTAS, ...SHAPES].map((name) => [name, limitOf(standing, name)?.toString() ?? ""])));
  const field = (name: Quota | Shape, placeholder: string): ReactNode => (
    <label key={name} className="bxs-limit">
      <span className="bxs-limit-name">{ABOUT[name].name}</span>
      <input className="cfg-input" inputMode="numeric" aria-label={ABOUT[name].name} placeholder={placeholder} value={typed[name] ?? ""} onChange={(event) => setTyped({ ...typed, [name]: event.target.value.replace(/[^0-9]/g, "") })} />
      <span className="dash-quiet">{ABOUT[name].about}</span>
    </label>
  );
  return (
    <EditDialog title="Limits" icon="gauge" about={`What ${whom} may use.`} saving={saving} refused={refused} onSave={() => onSave(withLimits(standing, typed))} onClose={onClose}>
      <Effect>Organizations made from now on start with these. The ones that exist keep their limits: change those on each organization.</Effect>
      <p className="dash-quiet">Leave a field empty for no limit. Type 0 to switch that thing off.</p>
      <div className="bxs-limits">{QUOTAS.map((name) => field(name, "Unlimited"))}</div>
      <span className="tst-divide">Simulations</span>
      <div className="bxs-limits">{SHAPES.map((name) => field(name, "10, the usual"))}</div>
    </EditDialog>
  );
}

export function SettingsAdmission(): ReactNode {
  const credentials = useCredentials();
  const admission = useDoor(useCallback(() => readAdmission(credentials), [credentials]));
  const vendors = useDoor(useCallback(() => readHeldVendors(credentials), [credentials]));
  const acting = useMove();
  const [whose, setWhose] = useState<Whose>("first");
  const [world, setWorld] = useState<World>("sandbox");
  const [editing, setEditing] = useState<"limits" | "lends" | null>(null);
  const close = useCallback(() => setEditing(null), []);

  if (admission.value === undefined) return admission.refused === null ? <p className="dash-quiet tst-none">Reading…</p> : <Refusal>{admission.refused}</Refusal>;
  const row = admission.value;
  const same = whose === "later" && (row.later === null || row.later === undefined);
  // A later organization with no row of its own gets the first's: editing starts from that.
  const side = (whose === "first" ? row.first : row.later) ?? row.first;
  const standing = side[world];
  const lends = standing?.lends ?? null;
  const mode = modeOf(lends);
  const whom = `${whose === "first" ? "a person's first organization" : "a person's later organizations"} in ${WORLD_NAMES[world].toLowerCase()}`;

  const write = (next: Admission): void => void acting.move(async () => (await saveAdmission(credentials, next), await admission.reread())).then(close, () => undefined);
  const put = (changed: Newborn): void => write(whose === "first" ? { ...row, first: { ...row.first, [world]: changed } } : { ...row, later: { ...side, [world]: changed } });

  return (
    <>
      <div className="bxs-choose">
        <span className="bxs-says">A new organization gets…</span>
        <div className="dash-switch" role="group" aria-label="Which organization">
          {(["first", "later"] as const).map((one) => (
            <button key={one} type="button" className={whose === one ? "dash-switch-on" : ""} onClick={() => setWhose(one)}>
              {one === "first" ? "A person's first" : "Their later ones"}
            </button>
          ))}
        </div>
        <div className="dash-switch" role="group" aria-label="Environment">
          {WORLDS.map((one) => (
            <button key={one} type="button" className={world === one ? "dash-switch-on" : ""} onClick={() => setWorld(one)}>
              {WORLD_NAMES[one]}
            </button>
          ))}
        </div>
      </div>
      <p className="dash-quiet bxs-lede">
        {same
          ? "Nothing different is set for later organizations: each one a person makes gets the same as their first. Change a limit below to give later ones their own, which is how one free trial per person works."
          : whose === "first"
            ? "Given once, the moment someone makes their first organization. Changing this never touches an organization that already exists."
            : "Given to the second organization a person makes, and every one after. Usually less than the first, so a trial is had once."}
      </p>
      {editing === null && <Refusal>{acting.refused}</Refusal>}

      <Section
        icon="gauge"
        title="Limits"
        about="What it may use. Monthly ones start again on the 1st, UTC."
        action={
          <button type="button" className="cfg-save tst-action" onClick={() => setEditing("limits")}>
            Change limits
          </button>
        }
      >
        {[...QUOTAS, ...SHAPES].map((name) => {
          const value = limitOf(standing, name);
          const shape = (SHAPES as readonly string[]).includes(name);
          return (
            <div key={name} className="tst-row bxs-row">
              <span className="tst-row-words">
                <span className="tst-row-name">{ABOUT[name].name}</span>
                <span className="tst-row-under">{ABOUT[name].about}</span>
              </span>
              <span className={value === 0 ? "bxs-value bxs-value-off" : value === null ? "bxs-value bxs-value-free" : "bxs-value"}>{limitSaid(name, value, shape)}</span>
            </div>
          );
        })}
      </Section>

      <Section
        icon="brain"
        title="Vendors it is lent"
        about="Whose keys its calls run on when it has not brought its own."
        action={
          <button type="button" className="cfg-save tst-action" onClick={() => setEditing("lends")}>
            Change
          </button>
        }
      >
        {mode === "all" && <p className="dash-quiet tst-none">Every vendor this deployment holds a key for.</p>}
        {mode === "none" && <p className="dash-quiet tst-none">None. It runs only on keys it brings itself.</p>}
        {mode === "some" &&
          (lends ?? []).map((entry) => {
            const said = lendSaid(entry);
            const held = vendors.value === undefined || vendors.value.includes(said.vendor);
            return (
              <div key={entry} className="tst-row bxs-row">
                <Mark letter={brandOf(said.vendor).charAt(0)} />
                <span className="tst-row-words">
                  <span className="tst-row-name">{brandOf(said.vendor)}</span>
                  <span className="tst-row-under dash-clip">{said.model === null ? "Every model" : said.model}</span>
                </span>
                <span className={`tst-status bxs-status tst-status-${held ? "held" : "waiting"}`}>{held ? "Lent" : "No key here"}</span>
              </div>
            );
          })}
      </Section>

      {whose === "later" && !same && (
        <div className="bxs-foot">
          <span className="dash-quiet">Later organizations have limits of their own, in both environments.</span>
          <ConfirmButton label="Give them the first's again" asks="Drop their own limits?" danger onConfirm={() => write({ ...row, later: null })} />
        </div>
      )}

      {editing === "limits" && <LimitsPanel key={`${whose}:${world}`} whom={whom} standing={standing} saving={acting.busy} refused={acting.refused} onSave={put} onClose={close} />}
      {editing === "lends" && <LendsPanel key={`${whose}:${world}`} whom={whom} held={vendors.value ?? []} lends={lends} saving={acting.busy} refused={acting.refused} onSave={(next) => put({ ...(standing ?? {}), lends: next })} onClose={close} />}
    </>
  );
}

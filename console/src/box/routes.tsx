/** Routes, the operator's: the numbers waiting for approval first, then every number the deployment answers, of every organization and both environments, to search and filter. */

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { useCredentials } from "@pinecall/core/credentials";
import { ConfirmButton } from "../apps/confirm";
import { useMove } from "../numbers/parts";
import { shown } from "../numbers/words";
import { Icon } from "../shell/icons";
import { Select } from "../ui/select";
import { readOrgs } from "./door";
import { approveNumber, readBoxNumbers, refuseNumber, type BoxNumber } from "./telephony-door";
import { cameIn, Head, OperatorPage, OrgLink, ringsOf, useDoor } from "./telephony-parts";

type Env = "all" | "production" | "sandbox";
const ENVS: readonly { env: Env; name: string }[] = [
  { env: "all", name: "Both" },
  { env: "production", name: "Production" },
  { env: "sandbox", name: "Sandbox" },
];
const EVERY_ORG = "";

const keyOf = (row: BoxNumber): string => `${row.org} ${row.env} ${row.channel} ${row.number}`;
const traceOf = (row: BoxNumber): string => `/box/traceback?number=${encodeURIComponent(row.number)}`;

/** Whether the words name the row: its number by digits alone, its org or its agent. */
function matches(row: BoxNumber, orgName: string, words: string): boolean {
  if (words === "") return true;
  const digits = words.replace(/\D/g, "");
  return `${row.org} ${orgName} ${row.agent}`.toLowerCase().includes(words) || (digits !== "" && row.number.replace(/\D/g, "").includes(digits));
}

function Board(): ReactNode {
  const credentials = useCredentials();
  const numbers = useDoor(useCallback(() => readBoxNumbers(credentials), [credentials]));
  // The orgs' names are a courtesy: without them a row says the slug.
  const orgs = useDoor(useCallback(() => readOrgs(credentials).catch(() => []), [credentials]));
  const mover = useMove();
  const [words, setWords] = useState("");
  const [org, setOrg] = useState(EVERY_ORG);
  const [env, setEnv] = useState<Env>("all");

  const names = useMemo(() => new Map((orgs.value ?? []).map((one) => [one.slug, one.name])), [orgs.value]);
  const nameOf = (slug: string): string => names.get(slug) ?? slug;
  const rows = numbers.value ?? [];
  const waiting = rows.filter((row) => !row.approved);
  const holders = [...new Set(rows.map((row) => row.org))].sort((one, other) => nameOf(one).localeCompare(nameOf(other)));
  const wanted = words.trim().toLowerCase();
  const found = rows.filter((row) => (org === EVERY_ORG || row.org === org) && (env === "all" || row.env === env) && matches(row, nameOf(row.org), wanted));
  const unanswered = rows.filter((row) => row.approved && !row.running).length;
  const refused = numbers.refused ?? mover.refused;

  const decide = (work: () => Promise<void>): void => void mover.move(work).then(numbers.reread, () => undefined);

  return (
    <>
      {refused !== null && (
        <p className="cfg-refused" role="alert">
          {refused}
        </p>
      )}

      <section className="tst-list" aria-label="Waiting for your approval">
        <Head icon="bell" title="Waiting for your approval" about="Numbers an organization pointed here from its own carrier. Nothing proves the number is theirs, so no call to one is answered until you approve it.">
          {waiting.length > 0 && <span className="tst-head-stands">{waiting.length} waiting</span>}
        </Head>
        {numbers.value === null && numbers.refused === null && <p className="dash-quiet tst-none">Reading…</p>}
        {waiting.map((row) => (
          <div key={keyOf(row)} className="tst-row tel-row">
            <span className="tst-row-words">
              <span className="tst-row-name">
                <span className="dash-clip">{shown(row.number)}</span>
                <span className="tst-tag">{row.env}</span>
              </span>
              <span className="tst-row-under">
                <OrgLink slug={row.org} name={nameOf(row.org)} /> wants {row.agent} to answer it{row.via == null ? "" : `, through ${row.via}`}. Approving makes it ring; refusing removes it from their numbers.
              </span>
            </span>
            <span className="tst-status tst-status-waiting tel-status">Waiting</span>
            <ConfirmButton label="Approve" asks="Let it ring?" onConfirm={() => decide(() => approveNumber(credentials, row.number, row.org))} />
            <ConfirmButton label="Refuse" asks="Remove the number?" danger onConfirm={() => decide(() => refuseNumber(credentials, row.number, row.org))} />
          </div>
        ))}
        {numbers.value !== null && waiting.length === 0 && <p className="dash-quiet tst-none">Nothing waits for you.</p>}
      </section>

      <section className="tst-list" aria-label="Every number">
        <Head icon="route" title="Every number" about="Each number this deployment answers, whose it is, which agent picks up, and whether a call to it would be answered right now.">
          {rows.length > 0 && <span className="tst-head-stands">{unanswered === 0 ? `${rows.length} numbers, all answered` : `${unanswered} of ${rows.length} not answered`}</span>}
        </Head>
        <div className="tst-tools tel-tools">
          <label className="tst-search">
            <Icon name="search" size={14} />
            <input aria-label="Search numbers" placeholder="Search a number, an organization or an agent" value={words} onChange={(event) => setWords(event.target.value)} />
          </label>
          <div className="tel-pick">
            <Select label="Organization" items={[{ value: EVERY_ORG, label: "Every organization" }, ...holders.map((slug) => ({ value: slug, label: nameOf(slug), detail: slug === nameOf(slug) ? undefined : slug }))]} value={org} onChange={setOrg} />
          </div>
          <div className="dash-switch" role="tablist" aria-label="Environment">
            {ENVS.map((one) => (
              <button key={one.env} type="button" role="tab" aria-selected={env === one.env} className={env === one.env ? "dash-switch-on" : ""} onClick={() => setEnv(one.env)}>
                {one.name}
              </button>
            ))}
          </div>
        </div>
        {found.map((row) => {
          const rings = ringsOf(row);
          return (
            <div key={keyOf(row)} className="tst-row tel-row">
              <span className="tst-row-words">
                <span className="tst-row-name">
                  <span className="dash-clip">{shown(row.number)}</span>
                  <span className="tst-tag">{row.env}</span>
                  {row.channel !== "phone" && <span className="tst-tag">{row.channel === "whatsapp" ? "WhatsApp" : row.channel}</span>}
                </span>
                <span className="tst-row-under">
                  <OrgLink slug={row.org} name={nameOf(row.org)} />, answered by {row.agent}. {cameIn(row)}
                  {row.via == null ? "" : `, through ${row.via}`}.
                </span>
                {rings.mood !== "held" && <span className="tst-row-under tel-why">{rings.why}</span>}
              </span>
              <span className={`tst-status tst-status-${rings.mood} tel-status`} title={rings.why}>
                {rings.said}
              </span>
              <Link to={traceOf(row)} className="app-button tel-go">
                Trace its calls
              </Link>
            </div>
          );
        })}
        {numbers.value !== null && rows.length === 0 && <p className="dash-quiet tst-none">No number yet. An organization adds one from its own Numbers page.</p>}
        {rows.length > 0 && found.length === 0 && <p className="dash-quiet tst-none">Nothing matches. Clear the search or the filters.</p>}
        <p className="dash-quiet tel-note">Nothing here moves a number. To send one to another agent or let it go, open its organization's Numbers page, which changes the carrier and the route together.</p>
      </section>
    </>
  );
}

export function RoutesPage(): ReactNode {
  return (
    <OperatorPage>
      <Board />
    </OperatorPage>
  );
}

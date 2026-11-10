/** What the Privacy tabs share: a section's head, a moment written out, a count with its noun, and a teammate named by id. */

import { useEffect, useState, type ReactNode } from "react";

import { useCredentials } from "@pinecall/core/credentials";
import { readMembers } from "@pinecall/core/members";
import { useOrg } from "../lib/org";
import { Icon, type IconName } from "../shell/icons";

export function Head({ icon, title, about, children }: { icon: IconName; title: string; about: string; children?: ReactNode }): ReactNode {
  return (
    <header className="tst-head">
      <span className="tst-head-mark" aria-hidden="true">
        <Icon name={icon} size={16} />
      </span>
      <span className="tst-head-words">
        <span className="tst-head-title">{title}</span>
        <span className="tst-head-about">{about}</span>
      </span>
      {children}
    </header>
  );
}

/** `Nov 8, 2026, 2:41 PM`, from a unix time. */
export function dayAndTime(at: number): string {
  return new Date(at * 1000).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

/** `1 call`, `3 calls`. */
export function many(count: number, noun: string, plural: string = `${noun}s`): string {
  return `${count.toLocaleString("en-US")} ${count === 1 ? noun : plural}`;
}

export type Names = ReadonlyMap<string, string>;

/** The org's people by id, for a key that may read the team; empty until read, and for a key that may not. */
export function useNames(): Names {
  const credentials = useCredentials();
  const mayRead = useOrg().whose?.scopes.includes("team") ?? false;
  const [names, setNames] = useState<Names>(new Map());
  useEffect(() => {
    if (!mayRead) return;
    let gone = false;
    readMembers(credentials).then((members) => !gone && setNames(new Map(members.map((one) => [one.id, one.name || one.email]))), () => undefined);
    return () => {
      gone = true;
    };
  }, [credentials, mayRead]);
  return names;
}

/** Who an id is: a member by name, Pinecall's operator, or what the gateway wrote (a key, the retention run). */
export function whoOf(names: Names, id: string): string {
  if (id === "operator") return "Pinecall operator";
  if (id.startsWith("m_")) return names.get(id) ?? "A teammate";
  return id;
}

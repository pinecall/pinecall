/** An email thread's subject for its row in the list: read once from the call's first entry, kept for the page's life. */

import { useEffect, useState } from "react";

import { read } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";

// A subject never changes once a call opened: every row asks once, whatever re-renders.
const KNOWN = new Map<string, Promise<string | null>>();

async function subjectOf(credentials: Parameters<typeof read>[0], call: string): Promise<string | null> {
  const page = await read(credentials, `/v1/calls/${encodeURIComponent(call)}/events`, { durable: "true", types: "call.started", limit: "1" });
  const entries = Reflect.get(Object(page), "entries");
  const started = Array.isArray(entries) ? (entries[0] as unknown) : undefined;
  const metadata = started === undefined ? undefined : Reflect.get(Object(Reflect.get(Object(started), "data")), "metadata");
  const subject = metadata === undefined ? undefined : Reflect.get(Object(metadata), "subject");
  return typeof subject === "string" && subject.trim() !== "" ? subject : null;
}

/** The subject of an email call, or null while it is read, for a call of another channel, or for one with none. */
export function useSubject(call: string, byEmail: boolean): string | null {
  const credentials = useCredentials();
  const [subject, setSubject] = useState<string | null>(null);
  useEffect(() => {
    if (!byEmail) return;
    let current = true;
    const asked = KNOWN.get(call) ?? subjectOf(credentials, call).catch(() => null);
    KNOWN.set(call, asked);
    void asked.then((found) => current && setSubject(found));
    return () => {
      current = false;
    };
  }, [credentials, call, byEmail]);
  return subject;
}

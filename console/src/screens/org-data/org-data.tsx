/** Privacy: the org's data, one tab each — its rules and what a call says first, consent and the list, export and erasure with their trail, who read what. */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { useWorld } from "../../lib/world";
import { Page, PageHead, Refused } from "../../ui";
import { readPolicy, readTrail, type Erasure, type PolicyRow } from "./door";
import { DoNotCallCard } from "./do-not-call";
import { EraseAContact, TakeItOut, Trail } from "./erasures";
import { OpeningCard } from "./opening";
import { ReadsCard } from "./reads";
import { RulesCard } from "./rules";
import "./org-data.css";

/** How long a call is kept, when and how often a number is rung, where consent is asked, and what a call says first. */
export function PrivacyRules(): ReactNode {
  const credentials = useCredentials();
  const { world } = useWorld();
  const [policy, setPolicy] = useState<PolicyRow | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  useEffect(() => {
    let gone = false;
    readPolicy(credentials).then(
      (kept) => !gone && setPolicy(kept),
      (failed: unknown) => !gone && setRefused(saidBy(failed)),
    );
    return () => {
      gone = true;
    };
  }, [credentials]);

  return (
    <Page tight>
      <PageHead title="Rules" ledeWidth={660} lede={`What this org keeps in ${world} and for how long, when and how often a number is rung, where consent is asked, and what every call says before the agent's greeting.`} />
      <Refused>{refused}</Refused>
      <RulesCard policy={policy} onSaved={setPolicy} onRefused={setRefused} />
      <OpeningCard policy={policy} onSaved={setPolicy} onRefused={setRefused} />
    </Page>
  );
}

/** Who said yes to being called, and the numbers that are never rung. */
export function PrivacyConsent(): ReactNode {
  const [refused, setRefused] = useState<string | null>(null);
  return (
    <Page tight>
      <PageHead title="Consent" ledeWidth={660} lede="Check whether a number agreed to be called, and keep the list of numbers that must never be called." />
      <Refused>{refused}</Refused>
      <DoNotCallCard onRefused={setRefused} />
    </Page>
  );
}

/**
 * The world taken out whole, a contact erased, and every erasure — from here, from a call's page,
 * from `pinecall data`, from the nightly retention run — as a row of the trail, which outlives the org.
 */
export function PrivacyErasures(): ReactNode {
  const credentials = useCredentials();
  const [trail, setTrail] = useState<Erasure[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);

  const reread = useCallback(async (): Promise<void> => {
    try {
      setTrail(await readTrail(credentials));
    } catch (failed) {
      setRefused(saidBy(failed));
    }
  }, [credentials]);

  useEffect(() => {
    void reread();
  }, [reread]);

  return (
    <Page tight>
      <PageHead
        title="Export & erase"
        ledeWidth={660}
        lede="Everything this world keeps, as one file; and a person's data gone. An erasure cannot be undone: the call's log, its facts, the memories it taught and its recording go in one transaction, and a row below says so."
      />
      <Refused>{refused}</Refused>
      <TakeItOut onRefused={setRefused} />
      <EraseAContact onErased={reread} onRefused={setRefused} />
      <Trail rows={trail} />
    </Page>
  );
}

/** Who read what: a person reading a call's log or recording, listening in, the operator. */
export function PrivacyReads(): ReactNode {
  const [refused, setRefused] = useState<string | null>(null);
  return (
    <Page tight>
      <PageHead title="Access log" ledeWidth={660} lede="Every time somebody read a call: its log, its recording, a seat listening in, the desk, an export, a read of memory — and the operator, off the box or in a traceback." />
      <Refused>{refused}</Refused>
      <ReadsCard onRefused={setRefused} />
    </Page>
  );
}

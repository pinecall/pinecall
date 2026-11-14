/** Run again: a simulated call that is over, placed again as it was on a new call. */

import { useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { placeAgain } from "./door";

/** The button, and the gateway's refusal beside it; `onStarted` is handed the new call, to watch. */
export function RunAgain({ call, onStarted }: { call: string; onStarted: (call: string) => void }): ReactNode {
  const credentials = useCredentials();
  const [placing, setPlacing] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const again = async (): Promise<void> => {
    setPlacing(true);
    setRefused(null);
    try {
      onStarted(await placeAgain(credentials, call));
    } catch (failed) {
      setRefused(saidBy(failed));
    } finally {
      setPlacing(false);
    }
  };

  return (
    <>
      {refused !== null && <span className="app-refused">{refused}</span>}
      <button type="button" className="app-button" disabled={placing} title="The same caller on the same line, with the same room behind it. A new call, billed as this one was." onClick={() => void again()}>
        {placing ? "Calling…" : "Run again"}
      </button>
    </>
  );
}

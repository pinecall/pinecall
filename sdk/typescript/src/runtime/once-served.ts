/** What a class does once its agent is registered: its declared base and melody pushed, then `static onServe` run. */

import type { Pinecall } from "../client/index.js";

import type { Agent } from "../agent/agent.js";
import type { Serve } from "../agent/served.js";
import { pushDeclaredDocs } from "./declared-docs.js";
import { uploadDeclaredHold } from "./declared-hold.js";

type Ctor = new () => Agent;

// Once the agent is registered, after every connect: what the class publishes for pages is kept by
// the gateway and asked again at no cost, so a reconnect runs it again rather than track what changed.
// The documents a class declares as its base are pushed once per process, before its onServe.
export function served(ctor: Ctor, pc: Pinecall, slug: string, report: ((line: string) => void) | undefined, file: string | undefined): void {
  const serve: Serve = {
    slug,
    record: (texts) => pc.recordLines(slug, texts),
    publish: (name, document) => pc.publish(slug, name, document),
    say: (line) => report?.(line),
  };
  const declared = ctor as unknown as typeof Agent;
  const onServe = declared.onServe.bind(ctor);
  let pushed = false;
  pc.onConnected(() => {
    const docs = pushed ? Promise.resolve() : pushDeclaredDocs(pc, declared, file, report).then(() => uploadDeclaredHold(pc, declared, file, slug, report));
    pushed = true;
    docs
      .then(() => onServe(serve))
      .catch((failed: unknown) => pc.onError(failed instanceof Error ? failed : new Error(String(failed))));
  });
}

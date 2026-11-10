/** A call open in the panel takes its agent's model and voice anew when the settings are saved while it is on, and says each change as a line of the conversation. */

import { useEffect } from "react";

import { post } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { StageChangedSchema } from "@pinecall/core/wire/events";
import { onSettingsSaved } from "../configure/door";
import { brandOf } from "../configure/vendors";

/**
 * While `call` is live, every save of `agent`'s settings asks the gateway for that call to run on
 * them. What changed comes back on the call's own log (`stage.changed`); a call that could not take
 * them says so there too, so nothing is drawn from this answer.
 */
export function useSettingsFollowed(agent: string, call: string | null, live: boolean): void {
  const credentials = useCredentials();
  useEffect(() => {
    if (call === null || !live) return undefined;
    return onSettingsSaved((saved) => {
      if (saved !== agent) return;
      // A key that may not write vendors, or a call already over: the call goes on as it was.
      post(credentials, `/v1/calls/${encodeURIComponent(call)}/stages`, {}).catch(() => undefined);
    });
  }, [credentials, agent, call, live]);
}

const STAGES: Readonly<Record<string, string>> = { llm: "Model", stt: "Transcriber", tts: "Voice" };

/** `stage.changed` as one line: what the stage runs on now, or for the ears that it waits for the next call. */
export function stageSaid(data: unknown): string | null {
  const read = StageChangedSchema.safeParse(data);
  if (!read.success) return null;
  const { stage, vendor, model, voice, applied } = read.data;
  const on = [brandOf(vendor), model, voice].filter((part) => part != null && part !== "").join(" · ");
  return applied ? `${STAGES[stage]} changed to ${on}, from the next turn` : `${STAGES[stage]} changed to ${on}: it runs on the next call`;
}

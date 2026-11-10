/** Advanced's form as text while it is edited, read from the settings and turned back into them: an empty field is a setting taken out. */

import type { TuningBody } from "../configure/door";

export interface Draft {
  endOfTurn: string;
  silenceMs: string;
  eot: string;
  eager: string;
  words: string;
  interruptMs: string;
  silenceTimeout: string;
  idleLines: string;
  idleAfter: string;
  idleTimes: string;
  voicemail: boolean;
  voicemailMessage: string;
  sttFallbacks: readonly string[];
  ttsFallbacks: readonly string[];
  minutes: string;
  record: boolean;
  llmTimeout: string;
}

const shown = (value: number | null | undefined): string => (value == null ? "" : String(value));
const number = (text: string): number | null => (text.trim() === "" ? null : Number(text));
const lines = (text: string): string[] =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");

export function draftOf(config: TuningBody): Draft {
  return {
    endOfTurn: config.end_of_turn ?? "",
    silenceMs: shown(config.turn?.endpointing_ms),
    eot: shown(config.turn?.eot_threshold),
    eager: shown(config.turn?.eager_eot_threshold),
    words: shown(config.turn?.min_interruption_words),
    interruptMs: shown(config.turn?.min_interruption_ms),
    silenceTimeout: shown(config.silence_timeout_s),
    idleLines: (config.idle?.says ?? []).join("\n"),
    idleAfter: shown(config.idle?.after_s),
    idleTimes: shown(config.idle?.times),
    voicemail: config.voicemail != null,
    voicemailMessage: config.voicemail?.message ?? "",
    sttFallbacks: config.stt_fallbacks ?? [],
    ttsFallbacks: config.tts_fallbacks ?? [],
    minutes: config.max_duration_s == null ? "" : String(config.max_duration_s / 60),
    record: config.record ?? true,
    llmTimeout: shown(config.llm_timeout_s),
  };
}

function turnOf(draft: Draft): NonNullable<TuningBody["turn"]> | null {
  const turn: NonNullable<TuningBody["turn"]> = {};
  const silence = number(draft.silenceMs);
  const eot = number(draft.eot);
  const eager = number(draft.eager);
  const words = number(draft.words);
  const interrupt = number(draft.interruptMs);
  if (silence !== null) turn.endpointing_ms = Math.round(silence);
  if (eot !== null) turn.eot_threshold = eot;
  if (eager !== null) turn.eager_eot_threshold = eager;
  if (words !== null) turn.min_interruption_words = Math.round(words);
  if (interrupt !== null) turn.min_interruption_ms = Math.round(interrupt);
  return Object.keys(turn).length === 0 ? null : turn;
}

function idleOf(draft: Draft): NonNullable<TuningBody["idle"]> | null {
  const says = lines(draft.idleLines);
  if (says.length === 0) return null;
  const idle: NonNullable<TuningBody["idle"]> = { says };
  const after = number(draft.idleAfter);
  const times = number(draft.idleTimes);
  if (after !== null) idle.after_s = after;
  if (times !== null) idle.times = Math.round(times);
  return idle;
}

function voicemailOf(draft: Draft): NonNullable<TuningBody["voicemail"]> | null {
  if (!draft.voicemail) return null;
  const message = draft.voicemailMessage.trim();
  return message === "" ? {} : { message };
}

/** The settings with the form over them; every setting the form does not draw goes back as it was. */
export function bodyOf(config: TuningBody, draft: Draft, was: Draft): TuningBody {
  const next: TuningBody = { ...config };
  const put = <K extends keyof TuningBody>(key: K, value: TuningBody[K] | null): void => {
    if (value === null) delete next[key];
    else next[key] = value;
  };
  put("turn", turnOf(draft));
  put("end_of_turn", draft.endOfTurn === "" ? null : (draft.endOfTurn as NonNullable<TuningBody["end_of_turn"]>));
  put("idle", idleOf(draft));
  put("voicemail", voicemailOf(draft));
  put("silence_timeout_s", number(draft.silenceTimeout));
  put("llm_timeout_s", number(draft.llmTimeout));
  put("stt_fallbacks", draft.sttFallbacks.length === 0 ? null : [...draft.sttFallbacks]);
  put("tts_fallbacks", draft.ttsFallbacks.length === 0 ? null : [...draft.ttsFallbacks]);
  const minutes = number(draft.minutes);
  put("max_duration_s", minutes === null ? null : Math.round(minutes * 60));
  if (draft.record !== was.record) next.record = draft.record;
  return next;
}

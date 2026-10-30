/** How a call opens and ends, and how a turn is cut: the Conversation tab, four cards — the opening, hanging up, turns, the call. */

import type { ReactNode } from "react";

import { Check, Input, Label, Segmented, Select, SelectItem, TextArea } from "../../ui";
import { Advanced } from "./advanced";
import { FixedByTheClass } from "./plugin";
import type { Change, Typed } from "./typed";

const OPENINGS = [
  { value: "say", label: "Say these words" },
  { value: "reply", label: "Let the model improvise" },
] as const;

const HANGS_UP = [
  { value: "never", label: "Never" },
  { value: "any", label: "Whenever it judges" },
  { value: "when", label: "When…" },
] as const;

// The bands the ears take the two confidences in (the gateway refuses outside them).
const SURE = ["0.5", "0.6", "0.7", "0.8", "0.9"];
const EAGER = ["0.3", "0.4", "0.5", "0.6", "0.7"];

// The two numbers of a turn, as lists of values that run: the ears take 500 to 3000 ms of silence
// (soniox/stt.py:145), and the runtime's defaults are 1000 ms and two words.
const SILENCES = ["500", "700", "1000", "1500", "2000", "3000"];
const WORDS = ["1", "2", "3", "4", "5"];

// The longest a voice call runs, in seconds, as the runtime takes it: no limit, or a minute to an
// hour. The empty one falls through to the team's, and the team's to the runtime's ten minutes.
const LIMITS = ["300", "900", "1200", "1800", "2700", "3600"];

// Three and not two: a corner that has said nothing is not a corner that has said no. The empty
// one falls through to the team's, and the team's to the runtime's own answer, which is to keep it.
const RECORDINGS = [
  { value: "", label: "Not set" },
  { value: "on", label: "Keep the audio" },
  { value: "off", label: "Keep none" },
] as const;

/** A card's title and the one line under it saying what it holds. */
function Head({ title, blurb }: { title: string; blurb: string }): ReactNode {
  return (
    <div className="set-section-head">
      <h2 className="set-section-title">{title}</h2>
      <p className="set-section-blurb">{blurb}</p>
    </div>
  );
}

export function ConversationSection({
  typed,
  wordsOnly,
  fixed,
  change,
}: {
  typed: Typed;
  /** A key that opens words and not the pipeline: the words of the opening, and nothing else here. */
  wordsOnly: boolean;
  /** The settings the agent's class declares itself: shown, never edited. */
  fixed: ReadonlySet<string>;
  change: Change;
}): ReactNode {
  return (
    <>
      <section className="set-section">
        <Head title="Opening" blurb="The first thing a caller hears." />
        {fixed.has("greeting") ? (
          <FixedByTheClass label="Opening" />
        ) : (
          <>
            {!wordsOnly && <Segmented options={OPENINGS} value={typed.opening} onChange={(picked) => change("opening", picked)} />}
            {typed.opening === "say" || wordsOnly ? (
              <Input value={typed.say} aria-label="Opening" placeholder="The exact words the caller hears first" onChange={(event) => change("say", event.target.value)} />
            ) : (
              <TextArea value={typed.reply} rows={2} aria-label="Opening" placeholder="Empty: the model opens on its prompt alone. Or what it is told about this opening" onChange={(event) => change("reply", event.target.value)} />
            )}
            <p className="set-help set-help-under">
              {typed.opening === "say" || wordsOnly
                ? "Said before the model runs, so the caller hears it at once."
                : "The model finds its own opening, on its prompt or this instruction. It costs a model round trip before the caller hears anything."}
            </p>
            {!wordsOnly && (
              <Check checked={typed.interruptible} onChange={(checked) => change("interruptible", checked)}>
                The caller may cut the opening short
              </Check>
            )}
          </>
        )}
      </section>
      {!wordsOnly && (
        <>
          <section className="set-section">
            <Head title="Hanging up" blurb="When the agent may end the call itself." />
            {fixed.has("hangup") ? (
              <FixedByTheClass label="May hang up" />
            ) : (
              <>
                <Segmented options={HANGS_UP} value={typed.hangs_up} onChange={(picked) => change("hangs_up", picked)} />
                {typed.hangs_up === "when" && (
                  <Input value={typed.hangup} aria-label="May hang up when" placeholder="the person has what they came for, or asks you to end the call" onChange={(event) => change("hangup", event.target.value)} />
                )}
              </>
            )}
          </section>
          <section className="set-section">
            <Head title="Turns" blurb="How quickly the agent answers, and what counts as an interruption." />
            {fixed.has("turn") ? (
              <FixedByTheClass label="How a turn ends" />
            ) : (
              <>
                <div className="set-row">
                  <div className="set-field">
                    <Label>Silence that ends a turn</Label>
                    <Select value={typed.endpointing_ms} aria-label="Silence that ends a turn" onValueChange={(value) => change("endpointing_ms", value)}>
                      <SelectItem value="">Default · 1 s</SelectItem>
                      {listed(SILENCES, typed.endpointing_ms).map((ms) => (
                        <SelectItem key={ms} value={ms}>
                          {Number(ms) / 1000} s
                        </SelectItem>
                      ))}
                    </Select>
                    <p className="set-help">Shorter answers faster, and cuts off a slow speaker.</p>
                  </div>
                  <div className="set-field">
                    <Label>Words before an interruption counts</Label>
                    <Select value={typed.min_interruption_words} aria-label="Words before an interruption counts" onValueChange={(value) => change("min_interruption_words", value)}>
                      <SelectItem value="">Default · 2 words</SelectItem>
                      {listed(WORDS, typed.min_interruption_words).map((words) => (
                        <SelectItem key={words} value={words}>
                          {words === "1" ? "1 word" : `${words} words`}
                        </SelectItem>
                      ))}
                    </Select>
                    <p className="set-help">A cough isn&apos;t an interruption.</p>
                  </div>
                </div>
                <Advanced>
                  <div className="set-row">
                    <div className="set-field">
                      <Label>How sure the ears must be</Label>
                      <Select value={typed.eot_threshold} aria-label="How sure the ears must be" onValueChange={(value) => change("eot_threshold", value)}>
                        <SelectItem value="">Runtime default</SelectItem>
                        {listed(SURE, typed.eot_threshold).map((sure) => (
                          <SelectItem key={sure} value={sure}>
                            {sure}
                          </SelectItem>
                        ))}
                      </Select>
                      <p className="set-help">For ears that end the turn themselves (Flux): the confidence it needs to end one. Higher waits for a caller who pauses mid-sentence.</p>
                    </div>
                    <div className="set-field">
                      <Label>When it may guess early</Label>
                      <Select value={typed.eager_eot_threshold} aria-label="When it may guess early" onValueChange={(value) => change("eager_eot_threshold", value)}>
                        <SelectItem value="">Runtime default</SelectItem>
                        {listed(EAGER, typed.eager_eot_threshold).map((eager) => (
                          <SelectItem key={eager} value={eager}>
                            {eager}
                          </SelectItem>
                        ))}
                      </Select>
                      <p className="set-help">The lower bar at which the model starts an answer that is thrown away if the caller carries on. Faster, and more model calls.</p>
                    </div>
                  </div>
                </Advanced>
              </>
            )}
          </section>
          <section className="set-section">
            <Head title="The call" blurb="How long a voice call may run, and whether its audio is kept." />
            <div className="set-row">
              {fixed.has("max_duration_s") ? (
                <FixedByTheClass label="Longest voice call" value={typed.max_duration_s === "0" ? "no limit" : typed.max_duration_s === "" ? null : `${Number(typed.max_duration_s) / 60} minutes`} />
              ) : (
                <div className="set-field">
                  <Label>Longest voice call</Label>
                  <Select value={typed.max_duration_s} aria-label="Longest voice call" onValueChange={(value) => change("max_duration_s", value)}>
                    <SelectItem value="">Default · 10 minutes</SelectItem>
                    {listed(LIMITS, typed.max_duration_s).filter((seconds) => seconds !== "0").map((seconds) => (
                      <SelectItem key={seconds} value={seconds}>
                        {Number(seconds) / 60} minutes
                      </SelectItem>
                    ))}
                    <SelectItem value="0">No limit</SelectItem>
                  </Select>
                  <p className="set-help">A minute before, it&apos;s told to wrap up. Written chats are never cut.</p>
                </div>
              )}
              {fixed.has("record") ? (
                <FixedByTheClass label="Recording" />
              ) : (
                <div className="set-field">
                  <Label>Recording</Label>
                  <Segmented options={RECORDINGS} value={typed.record} onChange={(picked) => change("record", picked)} />
                  <p className="set-help">The box records the whole room.</p>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </>
  );
}

// A value set from the terminal that is not on the list stays on it, so the form never drops it.
export function listed(values: readonly string[], set: string): readonly string[] {
  return set === "" || values.includes(set) ? values : [set, ...values];
}

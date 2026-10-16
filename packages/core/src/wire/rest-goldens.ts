/** A golden on the wire (runtime wire/rest/goldens.py): the turns it plays, what must follow each, and what holds at the end. */

import { z } from "zod";
import { EndedBySchema } from "./defs.js";

/**
 * What holds over the whole conversation, scored once every turn held: each field set is one
 * check, settled by code — except `judges`, the hang-up judges asked again by name of the golden's
 * call, the one field a model answers. A field left at its default is not sent.
 */
export const ExpectSchema = z.strictObject({
  tools: z.array(z.string()).optional(),
  not_tools: z.array(z.string()).optional(),
  not: z.array(z.string()).optional(),
  says: z.array(z.string()).optional(),
  says_any: z.array(z.string()).optional(),
  grounded: z.boolean().optional(),
  register: z.enum(["tu", "usted"]).nullable().optional(),
  judges: z.array(z.string()).optional(),
});

export type Expect = z.infer<typeof ExpectSchema>;

/** A fact of the tenant's backend, sent as the app's own `call.event` at its turn. */
export const InjectedEventSchema = z.strictObject({
  name: z.string(),
  data: z.record(z.string(), z.unknown()).optional(),
});

export type InjectedEvent = z.infer<typeof InjectedEventSchema>;

/** The next tool call of the turn is this one, with these arguments among its own (a subset), within this long of the turn's input. */
export const ToolStepSchema = z.strictObject({
  tool: z.string(),
  args: z.record(z.string(), z.unknown()).nullish(),
  within_ms: z.int().nullish(),
});

/** No call of this tool anywhere in the turn. */
export const NoToolStepSchema = z.strictObject({ no_tool: z.string() });

/** What the agent's next turn says: phrases checked by code, an intent by the judge model. */
export const ReplySchema = z.strictObject({
  says: z.array(z.string()).optional(),
  /** Any one of these is enough. */
  says_any: z.array(z.string()).optional(),
  not: z.array(z.string()).optional(),
  intent: z.string().nullish(),
  within_ms: z.int().nullish(),
});

export type Reply = z.infer<typeof ReplySchema>;

/** The agent's next turn, and what it must say. */
export const ReplyStepSchema = z.strictObject({ reply: ReplySchema });

/** The call ended in this turn, by this side. */
export const EndStepSchema = z.strictObject({ end: EndedBySchema });

/** After the step before it, the turn holds no other tool call and no other agent turn. */
export const NothingElseStepSchema = z.strictObject({ nothing_else: z.literal(true) });

/** One step of what must follow a turn: each names itself by its one required key. */
export const StepSchema = z.union([ToolStepSchema, NoToolStepSchema, ReplyStepSchema, EndStepSchema, NothingElseStepSchema]);

export type Step = z.infer<typeof StepSchema>;

/** One input — a caller's line or a backend's fact, exactly one — and, after a line only, what must follow it, in order. */
export const TurnSchema = z
  .strictObject({
    say: z.string().nullish(),
    event: InjectedEventSchema.nullish(),
    then: z.array(StepSchema).optional(),
  })
  .refine((turn) => (turn.say ?? null) === null !== ((turn.event ?? null) === null), "a turn says a line or sends an event: exactly one of say and event")
  .refine((turn) => (turn.event ?? null) === null || (turn.then ?? []).length === 0, "a turn that sends an event takes no then");

export type Turn = z.infer<typeof TurnSchema>;

/**
 * One scripted conversation: the state it opens in, its turns, and what holds at the end. The
 * first step that breaks cuts it: no later turn is played and `expect` is not scored.
 */
export const GoldenSchema = z.strictObject({
  name: z.string(),
  state: z.record(z.string(), z.unknown()).optional(),
  turns: z.array(TurnSchema).optional(),
  memory: z.array(z.string()).optional(),
  today: z.string().nullable().optional(),
  expect: ExpectSchema.optional(),
  promoted_from: z.string().nullable().optional(),
});

export type Golden = z.infer<typeof GoldenSchema>;

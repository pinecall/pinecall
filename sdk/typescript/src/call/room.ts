/** The call's room: its participants and the commands that act on them. */

import { type Camel, type CommandData } from "../wire/codec.js";
import { type CommandType } from "../wire/registry.js";

/** A participant's role in the call (the wire's `ParticipantKind`, src/wire/defs.ts). */
export type ParticipantKind = "caller" | "agent" | "supervisor" | "listener" | "sip";

/** One participant in the room. */
export interface Participant {
  identity: string;
  kind: ParticipantKind;
  name?: string;
  /** Join time from `participant.joined`, in ms. */
  joinedAt: number;
  /** Current voice activity, from `participant.speaking`. */
  speaking: boolean;
}

/** Sends one command on the wire, bound to its call. */
export type Commander = <K extends CommandType>(type: K, data: Camel<CommandData<K>>) => void;

/** Commands for one participant. Returned by `call.participant(identity)`. */
export class ParticipantHandle {
  constructor(
    readonly identity: string,
    private readonly send: Commander,
  ) {}

  /** Mute for the rest of the call. There is no unmute; invite the leg again instead. */
  mute(): void {
    this.send("participant.mute", { identity: this.identity });
  }

  /** Remove from the room. Removing the caller ends the call. */
  remove(): void {
    this.send("participant.remove", { identity: this.identity });
  }
}

/** Current participants, reduced from the room's log entries. Reads are local; verbs send commands. */
export class Room {
  readonly #participants = new Map<string, Participant>();

  constructor(private readonly send: Commander) {}

  /** Participants in join order. */
  get participants(): Participant[] {
    return [...this.#participants.values()];
  }

  /** The caller, if one has joined. */
  get caller(): Participant | undefined {
    return this.participants.find((one) => one.kind === "caller");
  }

  /** Whether a participant of this kind is present, e.g. `has("supervisor")`. */
  has(kind: ParticipantKind): boolean {
    return this.participants.some((one) => one.kind === kind);
  }

  /** A participant by identity. */
  get(identity: string): Participant | undefined {
    return this.#participants.get(identity);
  }

  /** Invite a number as a SIP leg, or an identity as a participant. */
  invite(to: string, options: { kind: "sip" | "participant" }): void {
    this.send("room.invite", { to, kind: options.kind });
  }

  /** Record a join. Re-joining under the same identity replaces the entry. */
  joined(data: { identity: string; kind: ParticipantKind; name?: string }, at: number): void {
    const one: Participant = { identity: data.identity, kind: data.kind, joinedAt: at, speaking: false };
    if (data.name !== undefined) one.name = data.name;
    this.#participants.set(data.identity, one);
  }

  /** Record a departure. */
  left(identity: string): void {
    this.#participants.delete(identity);
  }

  /** Update voice activity. Unknown identities are ignored. */
  speaking(identity: string, speaking: boolean): void {
    const one = this.#participants.get(identity);
    if (one !== undefined) one.speaking = speaking;
  }
}

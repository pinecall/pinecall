/** A tool that stops to ask: its call is answered with the question, and its function goes on when the model gives the answer. */

import { AsyncLocalStorage } from "node:async_hooks";

import type { ToolSpec } from "../wire/defs.js";

import type { Asked } from "../agent/screen.js";
import { askingFor, givenWith, givingTool, tasksOf, type Task } from "../agent/tasks.js";
import { DeclarationRefused } from "../agent/tools.js";

import { ToolFailed } from "./run-tool.js";

// One tool call that is running: its function, and who is told when it stops to ask.
interface Frame {
  /** The tool whose function this is. */
  tool: string;
  running: Promise<unknown>;
  asked: (question: string) => void;
}

interface Waiting {
  task: Task<unknown>;
  frame: Frame;
  give: (value: unknown) => void;
  drop: (why: Error) => void;
}

const FRAME = new AsyncLocalStorage<Frame>();

const NOT_IN_A_TOOL = "ask is for inside a tool: the tool's call is what the question is answered on";

/** The tasks a call may ask for: its class's, and with a team every member's, once each. */
export function tasksOn(ctor: Function, team?: ReadonlyMap<Function, string>): Task<unknown>[] {
  return [...new Set((team === undefined ? [ctor] : [...team.keys()]).flatMap(tasksOf))];
}

/** The tools a set of tasks is given with; a name an agent's own tool has is refused. */
export function givingTools(tasks: readonly Task<unknown>[], taken: readonly string[]): ToolSpec[] {
  const clash = tasks.find((asked) => taken.includes(givenWith(asked)));
  if (clash !== undefined) throw new DeclarationRefused(`the task ${clash.name} is given with ${givenWith(clash)}, and an agent declares a tool of that name`);
  return tasks.map(givingTool);
}

/**
 * The asking of one call. A tool that asks has its call answered at once, with the question; the
 * model asks the caller, and the tool it gives the answer with is answered with what the first
 * tool's function finally returned (`{ finished: <the tool>, result }`), or with its next question.
 */
export class Asking {
  #waiting: Waiting | undefined;
  #refused: string | undefined;

  constructor(private readonly tasks: readonly Task<unknown>[]) {}

  /** The one tool open while something is asked for; undefined when nothing is. */
  get open(): ToolSpec | undefined {
    return this.#waiting === undefined ? undefined : givingTool(this.#waiting.task);
  }

  /** What is asked for now, for a screen that draws it as a form. */
  get asked(): Asked | undefined {
    const asked = this.#waiting?.task;
    if (asked === undefined) return undefined;
    return { task: asked.name, asks: asked.asks, fields: { ...asked.fields }, ...(this.#refused === undefined ? {} : { refused: this.#refused }) };
  }

  /**
   * The caller's page gave the answer, in the model's place: the waiting tool goes on. Answers what the
   * model is to be told, or undefined when the page gave a task nobody asked for or one its check refused.
   */
  async givenByPage(task: unknown, given: unknown): Promise<string | undefined> {
    const waiting = this.#waiting;
    if (waiting === undefined || waiting.task.name !== task || typeof given !== "object" || given === null) return undefined;
    try {
      const ended = await this.given(givenWith(waiting.task), given as Record<string, unknown>);
      if (typeof ended === "string") return `The caller gave ${waiting.task.asks} on their screen. ${ended}`;
      return `The caller gave ${waiting.task.asks} on their screen, and ${waiting.frame.tool} is done with this result: ${JSON.stringify((ended as { result: unknown }).result)}. Tell them how it went.`;
    } catch (refused) {
      if (!(refused instanceof ToolFailed)) throw refused;
      this.#refused = refused.message;
      return undefined;
    }
  }

  /** Whether a tool of that name gives one of the call's tasks. */
  gives(tool: string): boolean {
    return this.tasks.some((asked) => givenWith(asked) === tool);
  }

  /** Run the function of the tool `name`: what it returned, or the question it stopped at. */
  run(name: string, tool: () => Promise<unknown>): Promise<unknown> {
    const frame = { tool: name, asked: () => {} } as unknown as Frame;
    const stopped = this.#stops(frame);
    frame.running = FRAME.run(frame, tool);
    return Promise.race([frame.running, stopped]);
  }

  /** Ask for a task from inside a tool; resolves with what its check made of the model's answer. */
  ask<T>(asked: Task<T>): Promise<T> {
    const frame = FRAME.getStore();
    if (frame === undefined) return Promise.reject(new Error(NOT_IN_A_TOOL));
    if (!this.tasks.includes(asked as Task<unknown>)) return Promise.reject(new Error(`${asked.name} is not a task of this agent: name it in @agent({ tasks: [… ] })`));
    if (this.#waiting !== undefined) return Promise.reject(new Error(`${this.#waiting.task.name} is being asked for: one question at a time`));
    return new Promise<T>((give, drop) => {
      this.#waiting = { task: asked as Task<unknown>, frame, give: give as (value: unknown) => void, drop };
      frame.asked(askingFor(asked as Task<unknown>));
    });
  }

  /** The model gave the answer: the waiting tool goes on, and this call is answered with how it ended. */
  async given(tool: string, args: Record<string, unknown>): Promise<unknown> {
    const waiting = this.#waiting;
    if (waiting === undefined || givenWith(waiting.task) !== tool) throw new ToolFailed(`${tool}: nothing is being asked for with it now`);
    const missing = Object.keys(waiting.task.fields).filter((field) => typeof args[field] !== "string");
    if (missing.length > 0) throw new ToolFailed(`${tool}: ${missing.join(", ")} must be given, in words`);
    let value: unknown;
    try {
      value = await waiting.task.check(args as Record<string, string>);
    } catch (refused) {
      throw new ToolFailed(refused instanceof Error ? refused.message : String(refused));
    }
    this.#waiting = undefined;
    this.#refused = undefined;
    const stopped = this.#stops(waiting.frame);
    waiting.give(value);
    // Said as the first tool's result, by its name: read bare, the model takes it for the answer's own and calls the first tool again.
    return Promise.race([waiting.frame.running.then((result) => ({ finished: waiting.frame.tool, result })), stopped]);
  }

  /** The call ended with a question open: the tool that asked is told. */
  abandon(): void {
    const waiting = this.#waiting;
    this.#waiting = undefined;
    // The tool's call was answered already: nobody is left to hear what its function throws now.
    waiting?.frame.running.catch(() => {});
    waiting?.drop(new Error(`the call ended before the caller gave ${waiting.task.asks}`));
  }

  #stops(frame: Frame): Promise<string> {
    return new Promise<string>((resolve) => (frame.asked = resolve));
  }
}

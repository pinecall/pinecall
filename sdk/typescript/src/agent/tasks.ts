/** A task: one thing a tool needs from the caller before it can finish, asked for in the middle of the tool. */

import type { ToolSpec } from "../wire/defs.js";

import { DeclarationRefused } from "./tools.js";

/** What a task is made of. */
export interface TaskSpec<T, F extends string = string> {
  /** Its name, which names its tool: `email` is given with `give_email`. */
  name: string;
  /** What is asked for, as the model reads it: `"the caller's email address"`. */
  asks: string;
  /** How to ask for it: `"Spell it back and wait for a yes."`. */
  how?: string;
  /** What the model gives, each field with what it is. Every one is a string. */
  fields: Record<F, string>;
  /** What the tool is handed, out of what the model gave. One that throws tells the model why, and it asks again. */
  check(given: Record<F, string>): T | Promise<T>;
}

/** A task a tool asks with: `const email = await this.ask(GetEmail)`. */
export type Task<T> = Readonly<TaskSpec<T>>;

const A_NAME = /^[a-z][a-z0-9_]*$/;
const GIVE = "give_";

/** A task of your own: `task({ name: "plate", asks: "the car's plate", fields: { plate: "…" }, check: ({ plate }) => plate })`. */
export function task<T, F extends string = string>(spec: TaskSpec<T, F>): Task<T> {
  if (typeof spec?.name !== "string" || !A_NAME.test(spec.name)) throw new DeclarationRefused("a task's name is lowercase letters, digits and underscores: it names the tool the model gives it with");
  if (typeof spec.asks !== "string" || spec.asks.trim() === "") throw new DeclarationRefused(`the task ${spec.name} says what it asks for: asks: "the caller's email address"`);
  if (Object.keys(spec.fields ?? {}).length === 0) throw new DeclarationRefused(`the task ${spec.name} names what the model gives: fields: { email: "the address as it is typed" }`);
  if (typeof spec.check !== "function") throw new DeclarationRefused(`the task ${spec.name} has a check: what the tool is handed, out of what the model gave`);
  return Object.freeze({ ...spec }) as unknown as Task<T>;
}

/** The tasks a class declares: `@agent({ tasks: [GetEmail] })`. */
export function tasksOf(ctor: Function): Task<unknown>[] {
  const declared = (ctor as { tasks?: unknown }).tasks;
  if (declared === undefined) return [];
  if (!Array.isArray(declared) || declared.some((one) => typeof (one as Task<unknown>)?.check !== "function")) {
    throw new DeclarationRefused(`${ctor.name}: tasks is a list of tasks, like [GetEmail, GetPhone]`);
  }
  return declared as Task<unknown>[];
}

/** The name of the tool a task is given with. */
export function givenWith(asked: Task<unknown>): string {
  return `${GIVE}${asked.name}`;
}

/** The tool a task is given with, as it is declared. */
export function givingTool(asked: Task<unknown>): ToolSpec {
  const fields = Object.entries(asked.fields);
  return {
    name: givenWith(asked),
    description: `Give ${asked.asks}, once the caller gave it to you. Never guess it and never make one up.`,
    parameters: {
      type: "object",
      properties: Object.fromEntries(fields.map(([name, description]) => [name, { type: "string", description }])),
      required: fields.map(([name]) => name),
    },
  };
}

/** What the model is told when a tool stops to ask. */
export function askingFor(asked: Task<unknown>): string {
  return `This is not done yet: it needs ${asked.asks}. Ask the caller for it now.${asked.how === undefined ? "" : ` ${asked.how}`} Then call ${givenWith(asked)}.`;
}

const AN_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** The caller's email address, lowercased. */
export const GetEmail = task({
  name: "email",
  asks: "the caller's email address",
  how: "Spell it back to them letter by letter and wait for a yes.",
  fields: { email: "The address as it is typed, like ana@example.com: no spaces, no words like 'at' or 'dot'." },
  check: ({ email }) => {
    const address = email.trim().toLowerCase();
    if (!AN_EMAIL.test(address)) throw new Error(`"${email}" is not an email address. Ask them to say it again, slowly.`);
    return address;
  },
});

/** The caller's phone number, digits only, with its `+` when they gave a country code. */
export const GetPhone = task({
  name: "phone",
  asks: "a phone number to reach the caller at",
  how: "Read it back in groups of digits and wait for a yes.",
  fields: { number: "The number in digits, with its country code when they said one: +14155550142." },
  check: ({ number }) => {
    const digits = number.replace(/\D/g, "");
    if (digits.length < 7 || digits.length > 15) throw new Error(`"${number}" is not a phone number. Ask for it again, digit by digit.`);
    return number.trim().startsWith("+") ? `+${digits}` : digits;
  },
});

/** The caller's first and last name. */
export const GetName = task({
  name: "name",
  asks: "the caller's first and last name",
  how: "Ask how the last name is spelled when it is not a common one.",
  fields: { first: "Their first name.", last: "Their last name." },
  check: ({ first, last }) => {
    if (first.trim() === "" || last.trim() === "") throw new Error("Both names are needed. Ask for the one that is missing.");
    return { first: first.trim(), last: last.trim() };
  },
});

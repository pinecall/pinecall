/** The author attached to each state write, tracked per async context. */

import { AsyncLocalStorage } from "node:async_hooks";

// AsyncLocalStorage, not a shared stack: concurrent tools (and calls) interleave across awaits,
// and each write must be attributed to its own tool.
const author = new AsyncLocalStorage<string>();

// The model's id for the tool call a write is made in, so its cause names the call and not only the tool.
const toolCall = new AsyncLocalStorage<string>();

/** The current writer's name, or null outside any tool or hook. */
export function currentAuthor(): string | null {
  return author.getStore() ?? null;
}

/** Run `body` with every state write inside it attributed to `author`. */
export function withAuthor<T>(name: string, body: () => T): T {
  return author.run(name, body);
}

/** Async variant of `withAuthor`: the author holds across awaits inside `body`. */
export function withAuthorAsync<T>(name: string, body: () => Promise<T> | T): Promise<T> {
  return author.run(name, async () => await body());
}

const HOOK = "hook:";
const EVENT = "event:";

/** What `Change.author` says of a write inside a lifecycle hook. */
export function hookAuthor(hook: string): string {
  return `${HOOK}${hook}`;
}

/** What `Change.author` says of a write inside the handler of an outside event. */
export function eventAuthor(name: string): string {
  return `${EVENT}${name}`;
}

/** The hook an author names, or null when it is not a hook's. */
export function hookOf(author: string): string | null {
  return author.startsWith(HOOK) ? author.slice(HOOK.length) : null;
}

/** Whether an author is the handler of an outside event. */
export function isEvent(author: string): boolean {
  return author.startsWith(EVENT);
}

/** The model's id for the tool call running now, or null outside one. */
export function currentToolCall(): string | null {
  return toolCall.getStore() ?? null;
}

/** Run `body` as the tool call `id`: the writes inside it say which call made them. */
export function withToolCall<T>(id: string, body: () => T): T {
  return toolCall.run(id, body);
}

/** Thrown when state is assigned outside a tool or lifecycle hook. */

export class UnauthoredWrite extends Error {
  constructor(field: string) {
    super(
      `state field ${field} was assigned outside a tool and outside a lifecycle hook; ` +
        `tools are the only writers of state`,
    );
    this.name = "UnauthoredWrite";
  }
}

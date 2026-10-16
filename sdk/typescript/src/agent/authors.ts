/** The author attached to each state write, tracked per async context. */

import { AsyncLocalStorage } from "node:async_hooks";

// AsyncLocalStorage, not a shared stack: concurrent tools (and calls) interleave across awaits,
// and each write must be attributed to its own tool.
const author = new AsyncLocalStorage<string>();

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

/** The `@tool({...})` method decorator. */

import { withAuthorAsync } from "./authors.js";
import { lowerStage } from "./stages.js";
import { DeclarationRefused, register, type ToolOptions } from "./tools.js";

/**
 * Declare a method as a tool. Its JSDoc is the description and its signature the schema;
 * `when(state)` controls visibility (`stage` is shorthand for one). State writes are authored by it.
 */
export function tool<T extends object>(options: ToolOptions<T> = {}) {
  // A field has no descriptor: TypeScript calls a property decorator with two arguments.
  return function decorate(
    prototype: T,
    name: string,
    descriptor?: PropertyDescriptor,
  ): PropertyDescriptor {
    const method = descriptor?.value as ((...args: unknown[]) => unknown) | undefined;
    if (descriptor === undefined || typeof method !== "function") {
      throw new DeclarationRefused(`@tool goes on a method; ${name} is not one`);
    }
    // Attribute every state write during the call, including after awaits, to this tool.
    descriptor.value = function running(this: object, ...args: unknown[]): unknown {
      return withAuthorAsync(name, () => method.apply(this, args) as unknown);
    };
    register(prototype, { name, options: lowerStage(options), method });
    return descriptor;
  };
}

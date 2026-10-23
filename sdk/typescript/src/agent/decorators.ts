/** The `@tool({...})` method decorator, and the `@render(Prompt)`, `@voice`, `@llm`, `@realtime`, `@stt` and `@judge` class decorators. */

import { withAuthorAsync } from "./authors.js";
import { lowerStage } from "./stages.js";
import { DeclarationRefused, register, type ToolOptions } from "./tools.js";
import type { Child } from "../views/jsx-runtime.js";
import type { EndOfTurn } from "../wire/agent-config.js";

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

/** A prompt component whose props are the agent instance itself. */
export type Prompt<T> = (agent: T) => Child;

/**
 * Use `prompt` as the class's `render()`: `@render(SupportPrompt)` equals
 * `render() { return SupportPrompt(this); }`. The instance is passed whole (a spread would drop getters).
 */
export function render<T extends object>(prompt: Prompt<T>) {
  return function decorate(ctor: new (...args: never[]) => T): void {
    // Refuse both spellings on one class: one of them would be silently dead.

    if (Object.getOwnPropertyDescriptor(ctor.prototype, "render") !== undefined) {
      throw new DeclarationRefused(
        `${ctor.name} declares both @render(${prompt.name || "a prompt"}) and a render() method; ` +
          `two ways to answer one question — keep one`,
      );
    }
    Object.defineProperty(ctor.prototype, "render", {
      value: function render(this: T): Child {
        return prompt(this);
      },
      writable: true,
      configurable: true,
    });
  };
}

/** A plugin of the vendor's other than its default class, and its keyword arguments as the plugin names them. */
export interface Plugin {
  /** A class of the vendor's livekit plugin, dotted names allowed: `"responses.LLM"`. */
  builds?: string;
  /** Its keyword arguments, passed as given: `{ use_websocket: true }`. */
  options?: Record<string, unknown>;
}

/**
 * The voice, by its vendor and the vendor's own id for it: `@voice("cartesia", "<id>", { model: "sonic-2" })`.
 * Declared, it wins over the agent's settings.
 */
export function voice(provider: string, voiceId: string, more: Plugin & { model?: string } = {}) {
  return function decorate(ctor: Function): void {
    declare(ctor, "voice", { provider, voiceId, ...more });
  };
}

/**
 * The model that answers, `vendor/model` or a vendor alone:
 * `@llm("openai/gpt-5.4-mini", { builds: "responses.LLM", options: { use_websocket: true } })`.
 * Declared, it wins over the agent's settings.
 */
export function llm(model: string, more: Plugin & { temperature?: number } = {}) {
  return function decorate(ctor: Function): void {
    declare(ctor, "llm", { ...modelOf(model), ...more });
  };
}

/**
 * The model a voice call runs on alone, one that hears and speaks itself, `vendor/model` or a vendor
 * alone: `@realtime("xai/grok-voice-3.0", { options: { voice: "eve" } })`. A written call keeps the
 * `@llm`. Its options run on the org's own key for the vendor. Declared, it wins over the agent's settings.
 */
export function realtime(model: string, more: { options?: Record<string, unknown> } = {}) {
  return function decorate(ctor: Function): void {
    declare(ctor, "realtime", { ...modelOf(model), ...more });
  };
}

/**
 * The ears, `vendor/model` or a vendor alone: `@stt("soniox/stt-rt-v3", { endOfTurn: "smart-turn" })`.
 * `endOfTurn` is who says the caller's turn is over: `"stt"` the ears themselves (Deepgram Flux),
 * `"livekit"` or `"smart-turn"` a model on the worker. Declared, they win over the agent's settings.
 */
export function stt(model: string, more: Plugin & { endOfTurn?: EndOfTurn } = {}) {
  return function decorate(ctor: Function): void {
    const { endOfTurn, ...plugin } = more;
    declare(ctor, "stt", { ...modelOf(model), ...plugin, ...(endOfTurn === undefined ? {} : { endOfTurn }) });
  };
}

/**
 * The model the agent's calls are judged on, `vendor/model` or a vendor alone, over the org's choice
 * and the platform's. On a key of the org's own its evals are never billed — a local model too:
 * `@judge("openai/qwen3-32b", { options: { base_url: "http://gpu:8000/v1" } })`. Declared, it wins
 * over the agent's settings.
 */
export function judge(model: string, more: Plugin = {}) {
  return function decorate(ctor: Function): void {
    declare(ctor, "judge", { ...modelOf(model), ...more });
  };
}

// The model id keeps every slash after the vendor's: `livekit/openai/gpt-5-mini`.
function modelOf(named: string): { provider: string; model: string } {
  const slash = named.indexOf("/");
  if (slash < 0) return { provider: named, model: "" };
  return { provider: named.slice(0, slash), model: named.slice(slash + 1) };
}

// Refuse both spellings on one class, as @render does: one of them would be silently dead.
function declare(ctor: Function, field: "voice" | "llm" | "realtime" | "stt" | "judge", value: object): void {
  if (Object.hasOwn(ctor, field)) {
    throw new DeclarationRefused(`${ctor.name} declares both @${field}(…) and a static ${field}; keep one`);
  }
  Object.defineProperty(ctor, field, { value, writable: true, configurable: true, enumerable: true });
}

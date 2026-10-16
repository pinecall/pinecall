/** The bridge: mounts an Agent class on a Pinecall client, one instance per call. */

import { type Camel, type CommandData } from "../wire/codec.js";
import { type ToolSpec } from "../wire/defs.js";
import { type CommandType } from "../wire/registry.js";
import type { Agent as SdkAgent, AgentOptions, Call as SdkCall, Pinecall, Tool } from "../client/index.js";

import { Agent, onChange, onLog, recalled, seal, setCall, setLast } from "../agent/agent.js";
import { eventsOf } from "../agent/accepts.js";
import { visibilityOf } from "../agent/visibility.js";
import { CallWorld, type CallLine, type Searching } from "../call/call.js";
import { describe } from "../agent/docstrings.js";
import { searchesKnowledge } from "../agent/searching.js";
import { runHook, type Call as HookCall } from "../agent/lifecycle.js";
import { restore, snapshot, type LastCall, type Snapshot } from "../agent/state.js";
import { toolNamed } from "../agent/tools.js";
import { viewOf } from "../agent/view.js";
import { PROMPT_BLOCKS } from "../views/layout.js";
import { promptOf } from "../views/render.js";
import { inOrder, type Serving } from "./dispatch.js";
import { environmentOf, refuseTheEnvironment } from "./environment.js";
import { wordsRecalled } from "./recall.js";
import { runTool, ToolFailed } from "./run-tool.js";

/** Options for `mount()`. */
export interface MountOptions {
  pc: Pinecall;
  /** The class's source, so docstrings and parameter types survive compilation. */
  source?: string;
  /** The agent file's path; its extension selects the parser dialect. */
  file?: string;
  /** Override the slug derived from the class name. */
  slug?: string;
  /** Source for `this.last(contact)` on every instance of this mount. */
  last?: LastCall;
  /** False for a console, which serves only calls it opened itself. */
  takesUnclaimed?: boolean;
}

/** A mounted agent: its registered SDK agent and the instances serving live calls. */
export interface Mounted {
  slug: string;
  agent: SdkAgent;
  options: AgentOptions;
  /** The instance serving a call, while it lasts. */
  instanceOf(callId: string): Agent | undefined;
}

type Ctor = new () => Agent;

/** Sends one command for a call through the SDK agent. */
type Send = <K extends CommandType>(type: K, call: string, data: Camel<CommandData<K>>) => void;

// Last prompt and tools sent per call: re-sending identical text is a needless prompt-cache miss.
interface Sent {
  /** Last-sent text per block; an unsent block is empty, as the runtime starts it. */
  blocks: Map<string, string>;
  tools?: string;
}

interface Live {
  agent: Agent;
  sent: Sent;
  stop: (() => void)[];
  serving: Serving;
}

/** The slug an agent registers under: its `static slug`, or its class name in kebab-case. */
export function slugOf(ctor: Function): string {
  const declared = (ctor as { slug?: string }).slug;
  if (typeof declared === "string") return declared;
  return ctor.name
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1-$2")
    .toLowerCase();
}

function stateFieldsOf(ctor: Function): AgentOptions["stateFields"] {
  const declared = visibilityOf(ctor);
  return declared.length === 0 ? undefined : declared;
}

/**
 * Build the declaration sent to the gateway: tools, prompt layout, knowledge use, state fields,
 * events, view, and the environment the class declares. An environment field on the instance is
 * refused. `instance` is a throwaway probe; knowledge use is detected from `source` (or the class body).
 */
export function optionsFor(ctor: Ctor, tools: Tool[], instance: Agent = new ctor(), file?: string, source?: string): AgentOptions {
  const probe = instance as unknown as Record<string, unknown>;
  refuseTheEnvironment(probe);
  // Phone numbers are org rows managed with `pinecall numbers`, so a `phone` field is never sent.
  const options: AgentOptions = { tools, ...environmentOf(ctor) };
  if (searchesKnowledge(source ?? ctor.toString(), file)) options.usesKnowledge = true;
  // Always sent whole, so the runtime and console name blocks the same way.
  options.prompt = [...PROMPT_BLOCKS];
  const stateFields = stateFieldsOf(ctor);
  if (stateFields) options.stateFields = stateFields;
  const events = eventsOf(ctor);
  if (events.length > 0) options.events = events;
  // Only the name: the panel's content is rendered on demand by view.render (cli/ui/viewing.ts).
  const panel = viewOf(ctor);
  if (panel !== undefined) options.view = { name: panel.name };
  return options;
}

/**
 * Mount an agent class on a client. Each call gets its own instance, state and prompt.
 * Nothing is sent until `pc.connect()`.
 */
export function mount(
  ctor: Ctor,
  { pc, source, file, slug, last, takesUnclaimed = true }: MountOptions,
): Mounted {
  if (source !== undefined) describe(ctor, source, file);
  const name = slug ?? slugOf(ctor);
  const live = new Map<string, Live>();
  const probe = new ctor();
  const tools: Tool[] = probe.tools().map((spec) => ({
    ...(spec as unknown as Camel<ToolSpec>),
    run: (args, call) => call_(live, call, spec.name, args),
  }));
  const options = { ...optionsFor(ctor, tools, probe, file, source), takesUnclaimed };
  const agent = pc.agent(name, options);

  agent.on("call.started", (started, call) => {
    if (call !== null) {
      const send: Send = (type, id, data) => agent.command(type, id, data);
      const searching: Searching = (query, k) => pc.search(call.id, query, k);
      void start(ctor, live, call, send, searching, last, started.state ?? undefined);
    }
  });
  // A call handed over mid-conversation. If already served here (the gateway restarted), keep the
  // instance and resend the whole prompt, which the gateway may have lost.
  agent.on("call.attached", (attached, call) => {
    if (call === null) return;
    const held = live.get(call.id);
    if (held !== undefined) {
      held.sent = { blocks: new Map() };
      sync(held, call);
      return;
    }
    const send: Send = (type, id, data) => agent.command(type, id, data);
    const searching: Searching = (query, k) => pc.search(call.id, query, k);
    adopt(ctor, live, call, attached.state as Snapshot, send, searching, last);
  });
  agent.on("call.ended", (_payload, call) => {
    if (call !== null) void end(live, call);
  });
  return { slug: name, agent, options, instanceOf: (id) => live.get(id)?.agent };
}

// An unserved call means the line hung up: tell the model instead of throwing in the process.
async function call_(
  live: Map<string, Live>,
  call: SdkCall,
  name: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  const serving = live.get(call.id);
  if (serving === undefined) throw new ToolFailed(`${name}: this call is no longer being served`);
  const declaration = toolNamed(serving.agent, name);
  if (declaration === undefined) throw new ToolFailed(`${name}: this agent declares no such tool`);
  return runTool(serving.agent, declaration, args);
}

// Subscribe to changes only after the first sync, so onCall's writes go out as one prompt. The
// state the opener asked for is applied after onCall, which would overwrite it, and before the
// first render, so the model never sees the class's own state first.
async function start(
  ctor: Ctor,
  live: Map<string, Live>,
  call: SdkCall,
  send: Send,
  searching: Searching,
  last?: LastCall,
  openedIn?: Snapshot,
): Promise<void> {
  const link = serve(ctor, live, call, send, searching, last);
  await runHook(link.agent, "onCall", hookCall(call));
  if (openedIn !== undefined) link.agent.startIn(openedIn);
  call.setState(snapshot(link.agent));
  sync(link, call);
  follow(link, call);
}

// call.attached: take over a call from another process. Synchronous, because pending tool calls
// arrive next and must find the instance. No onCall; the gateway's snapshot is restored instead.
function adopt(
  ctor: Ctor,
  live: Map<string, Live>,
  call: SdkCall,
  state: Snapshot,
  send: Send,
  searching: Searching,
  last?: LastCall,
): void {
  const link = serve(ctor, live, call, send, searching, last);
  restore(link.agent, state);
  sync(link, call);
  follow(link, call);
}

function serve(
  ctor: Ctor,
  live: Map<string, Live>,
  call: SdkCall,
  send: Send,
  searching: Searching,
  last?: LastCall,
): Live {
  const agent = seal(new ctor());
  if (last !== undefined) setLast(agent, last);
  const world = new CallWorld(callLine(call), (type, data) => send(type, call.id, data), searching);
  setCall(agent, world);
  const serving: Serving = { agent, ctor, call: world, warned: new Set<string>(), queue: Promise.resolve() };
  const link: Live = { agent, sent: { blocks: new Map() }, stop: [], serving };
  live.set(call.id, link);
  return link;
}

function follow(link: Live, call: SdkCall): void {
  const { agent, serving } = link;
  const world = serving.call;
  link.stop.push(
    onChange(agent, (change) => {
      call.setState(snapshot(agent), [change.field]);
      // state.set has no cause field on the wire, so log it separately.
      const cause = world.cause;
      if (cause !== null) call.log("state.cause", { field: change.field, kind: "event", ...cause });
      sync(link, call);
    }),
    onLog(agent, (entry) => call.log(entry.name, dataOf(entry.data))),
    call.onAny((event) => {
      world.take(event.type, event.data as Record<string, unknown>, Date.now());
      if (event.type === "event.received") void received(serving, event.data);
      // Recalled memory is not state, so re-render explicitly.
      if (event.type === "memory.ops") {
        recalled(agent, wordsRecalled(event.data));
        sync(link, call);
      }
      // Re-render on the user's turn so the view reflects the turn being answered, not the previous
      // one. The gateway holds the LLM request while lookups run (runtime's session/lookups.py).
      if (event.type === "turn.user") sync(link, call);
      // A claim changes the view (the caller can now see the page) without moving a field.
      if (event.type === "call.claimed") sync(link, call);
    }),
  );
}

// Numbered per call: listeners receive events without the wire's seq.
async function received(serving: Serving, data: unknown): Promise<void> {
  const fact = data as { name: string; data: Record<string, unknown>; source: "app" | "participant"; identity?: string };
  await inOrder(serving, {
    name: fact.name,
    data: fact.data,
    source: fact.source,
    seq: serving.call.numbered(),
    ...(fact.identity === undefined ? {} : { identity: fact.identity }),
  });
}

async function end(live: Map<string, Live>, call: SdkCall): Promise<void> {
  const link = live.get(call.id);
  if (link === undefined) return;
  live.delete(call.id);
  for (const stop of link.stop) stop();
  await runHook(link.agent, "onEnd", hookCall(call));
  setCall(link.agent, null);
}

// Send only blocks whose text changed. Tools are compared as a whole: only `when` changes them mid-call.
function sync(serving: Live, call: SdkCall): void {
  const { blocks } = promptOf(serving.agent);
  for (const block of blocks) {
    if (block.text === (serving.sent.blocks.get(block.name) ?? "")) continue;
    serving.sent.blocks.set(block.name, block.text);
    call.setPrompt(block.name, block.text);
  }
  const visible = serving.agent.visibleTools();
  const key = JSON.stringify(visible);
  if (key !== serving.sent.tools) {
    serving.sent.tools = key;
    call.setTools(visible as unknown as Camel<ToolSpec>[]);
  }
}

function hookCall(call: SdkCall): HookCall {
  const hook: HookCall = { id: call.id, contact: call.contact?.id ?? call.from ?? "" };
  if (call.from !== null) hook.from = call.from;
  if (call.channel !== null) hook.channel = call.channel;
  if (call.medium !== null) hook.medium = call.medium;
  return hook;
}

// Adds `today` and `claimed`, which hookCall lacks; without them `this.call.today` is undefined.
function callLine(call: SdkCall): CallLine {
  return { ...hookCall(call), today: call.today, claimed: call.claimed };
}

// call.log requires an object, so wrap other values under `value`.
function dataOf(data: unknown): Record<string, unknown> {
  if (data === undefined) return {};
  if (typeof data === "object" && data !== null && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  return { value: data };
}

/** The bridge: mounts an Agent class on a Pinecall client, one instance per call. */

import { type Camel, type CommandData } from "../wire/codec.js";
import { type ToolSpec } from "../wire/defs.js";
import { type CommandType } from "../wire/registry.js";
import type { Agent as SdkAgent, AgentOptions, Call as SdkCall, Pinecall, Tool } from "../client/index.js";

import { Agent, changes, onChange, onLog, recalled, seal, setCall, setLast } from "../agent/agent.js";
import { setAppRules } from "../agent/app-rules.js";
import { eventsOf } from "../agent/accepts.js";
import { hookAuthor, withToolCall } from "../agent/authors.js";
import { visibilityOf } from "../agent/visibility.js";
import { CallWorld, type Searching } from "../call/call.js";
import { describe } from "../agent/docstrings.js";
import { searchesKnowledge } from "../agent/searching.js";
import { runHook } from "../agent/lifecycle.js";
import { restore, snapshot, type LastCall, type Snapshot } from "../agent/state.js";
import { toolNamed } from "../agent/tools.js";
import { viewOf } from "../agent/view.js";
import { PROMPT_BLOCKS } from "../views/layout.js";
import { promptOf } from "../views/render.js";
import { Asking, givingTools, tasksOn } from "./asking.js";
import { callLine, dataOf, hookCall } from "./call-line.js";
import { causeOf } from "./cause.js";
import { inOrder, type Serving } from "./dispatch.js";
import { harnessOf } from "../agent/harness.js";
import { holdConfigOf } from "./declared-hold.js";
import { environmentOf, refuseTheEnvironment } from "./environment.js";
import { answeredBy, mateNamed, MOST_PASSES, PASSED, ROUTED, teamTools, transfersOf, type Answering, type Team } from "./handoff.js";
import { served } from "./once-served.js";
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
  /** Where a line the class says for its person goes (`Serve.say`); a terminal's error stream when served. */
  report?: (line: string) => void;
  /** What the agent's voice app adds to its declaration: the greeting of its line, what it says to a silence. */
  declares?: Partial<AgentOptions>;
  /** The agents a call of this one may pass between, itself among them, each with its slug. */
  team?: Team;
  /** The rules the agent's voice app gives every agent of it, read into its prompt. */
  rules?: readonly string[];
  /** Its line's `answers`, when the line chooses who of the team serves each call. */
  answers?: Answering;
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

// The custom entries a view that failed to render, and a hook that threw, leave on their call.
const RENDER_FAILED = "render.failed";
const HOOK_FAILED = "hook.failed";

interface Live {
  agent: Agent;
  sent: Sent;
  /** The listeners that end with the call, before `onEnd` runs. */
  stop: (() => void)[];
  /** The log line forwarder, which outlives `onEnd` so a line logged there lands. */
  unlog: () => void;
  serving: Serving;
  /** The tools that offer this call to the agent's teammates, and how many times it was passed. */
  transfers: ToolSpec[];
  passes: number;
  team: Team | undefined;
  /** What a tool of this call stopped to ask the caller for. */
  asking: Asking;
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
  const options: AgentOptions = { tools, ...environmentOf(ctor), ...harnessOf(ctor) };
  const hold = holdConfigOf(ctor as unknown as typeof Agent, file);
  if (hold !== undefined) options.hold = hold;
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
  { pc, source, file, slug, last, takesUnclaimed = true, report, declares = {}, team, rules = [], answers }: MountOptions,
): Mounted {
  if (source !== undefined) describe(ctor, source, file);
  setAppRules(ctor, rules);
  const name = slug ?? slugOf(ctor);
  const live = new Map<string, Live>();
  const probe = new ctor();
  const own = team === undefined ? probe.tools() : teamTools(team);
  const tools: Tool[] = [...own, ...givingTools(tasksOn(ctor, team), own.map((spec) => spec.name))].map((spec) => ({
    ...(spec as unknown as Camel<ToolSpec>),
    run: (args, call, callId) => call_(live, call, spec.name, args, callId),
  }));
  const options = { ...optionsFor(ctor, tools, probe, file, source), ...declares, takesUnclaimed, saysDone: true };
  const agent = pc.agent(name, options);

  agent.on("call.started", (started, call) => {
    if (call !== null) {
      const send: Send = (type, id, data) => agent.command(type, id, data);
      const searching: Searching = (query, k) => pc.search(call.id, query, k);
      void start(ctor, live, call, send, searching, last, started.state ?? undefined, team, answers);
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
    adopt(ctor, live, call, attached.state as Snapshot, send, searching, last, team);
  });
  agent.on("call.ended", (_payload, call) => {
    if (call !== null) void end(live, call);
  });
  served(ctor, pc, name, report, file);
  return { slug: name, agent, options, instanceOf: (id) => live.get(id)?.agent };
}

// An unserved call means the line hung up: tell the model instead of throwing in the process.
async function call_(
  live: Map<string, Live>,
  call: SdkCall,
  name: string,
  args: Record<string, unknown>,
  callId: string,
): Promise<unknown> {
  const serving = live.get(call.id);
  if (serving === undefined) throw new ToolFailed(`${name}: this call is no longer being served`);
  // A tool that stopped to ask leaves one tool open, and the one that gives the answer opens the rest again.
  if (serving.asking.gives(name)) return serving.asking.given(name, args).finally(() => live.has(call.id) && sync(serving, call));
  const declaration = toolNamed(serving.agent, name);
  const mate = declaration === undefined && serving.team !== undefined ? mateNamed(name, serving.team) : undefined;
  if (mate !== undefined) return serving.serving.call.handoff(mate, args);
  if (declaration === undefined) throw new ToolFailed(`${name}: this agent declares no such tool`);
  return withToolCall(callId, () => serving.asking.run(name, () => runTool(serving.agent, declaration, args))).finally(() => live.has(call.id) && sync(serving, call));
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
  team?: Team,
  answers?: Answering,
): Promise<void> {
  // The line chooses while the caller hears its greeting; a choice it could not make is said on the log.
  const first = answers === undefined || team === undefined ? { agent: ctor } : await answeredBy(answers, callLine(call), ctor, team);
  if (first.agent !== ctor || first.why !== undefined) call.log(ROUTED, { to: team?.get(first.agent) ?? "", ...(first.why === undefined ? {} : { why: first.why }) });
  const link = serve(first.agent, live, call, send, searching, last, team);
  await hooked(call, "onCall", runHook(link.agent, "onCall", hookCall(call)));
  const author = hookAuthor("onCall");
  const wrote = changes(link.agent).some((change) => change.author === author);
  if (openedIn !== undefined) link.agent.startIn(openedIn);
  call.setState(snapshot(link.agent), undefined, wrote ? causeOf(author, link.serving.call) : undefined);
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
  team?: Team,
): void {
  const link = serve(ctor, live, call, send, searching, last, team);
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
  team?: Team,
): Live {
  const agent = seal(new ctor());
  if (last !== undefined) setLast(agent, last);
  const world = new CallWorld(callLine(call), (type, data) => send(type, call.id, data), searching);
  setCall(agent, world);
  const serving: Serving = { agent, ctor, call: world, warned: new Set<string>(), queue: Promise.resolve() };
  // Before the hooks run, so a line logged in onCall lands; stopped after onEnd.
  const unlog = onLog(agent, (entry) => call.log(entry.name, dataOf(entry.data)));
  const link: Live = { agent, sent: { blocks: new Map() }, stop: [], unlog, serving, transfers: team === undefined ? [] : transfersOf(ctor, team), passes: 0, team, asking: new Asking(tasksOn(ctor, team)) };
  world.askedBy((asked) => link.asking.ask(asked));
  if (team !== undefined) world.passedBy((to, data) => pass(link, call, team, to as Ctor, data));
  live.set(call.id, link);
  return link;
}

// One agent of a team takes the call from another: the instance, its listeners and its tools change, and the
// call itself stays, with what its agents share. The blocks already sent are compared, so only the ones that differ go.
async function pass(link: Live, call: SdkCall, team: Team, to: Ctor, data: Record<string, unknown>): Promise<string> {
  const slug = team.get(to);
  if (slug === undefined) throw new ToolFailed(`${to.name} is not of this call's team`);
  if (link.passes >= MOST_PASSES) throw new ToolFailed(`this call was passed ${MOST_PASSES} times already: answer the caller yourself`);
  for (const stop of link.stop.splice(0)) stop();
  link.unlog();
  setCall(link.agent, null);
  call.log(PASSED, { from: team.get(link.serving.ctor as Ctor) ?? "", to: slug, ...data });
  const agent = seal(new to());
  link.serving.call.handed = data;
  setCall(agent, link.serving.call);
  Object.assign(link.serving, { agent, ctor: to });
  Object.assign(link, { agent, passes: link.passes + 1, transfers: transfersOf(to, team), unlog: onLog(agent, (entry) => call.log(entry.name, dataOf(entry.data))) });
  await hooked(call, "onCall", runHook(agent, "onCall", hookCall(call)));
  call.setState(snapshot(agent));
  sync(link, call);
  follow(link, call);
  return `The call is ${slug}'s now: go on as ${slug}, without saying it was passed.`;
}

function follow(link: Live, call: SdkCall): void {
  const { agent, serving } = link;
  const world = serving.call;
  link.stop.push(
    onChange(agent, (change) => {
      call.setState(snapshot(agent), [change.field], causeOf(change.author, world));
      sync(link, call);
    }),
    call.onAny((event) => {
      world.take(event.type, event.data as Record<string, unknown>, Date.now());
      if (event.type === "event.received") void received(serving, call, event.data, event.seq ?? 0);
      // Recalled memory is not state, so re-render explicitly; then the hook reads what memory did.
      if (event.type === "memory.ops") {
        recalled(agent, wordsRecalled(event.data));
        sync(link, call);
        void hooked(call, "onMemory", runHook(agent, "onMemory", event.data.ops, hookCall(call)));
      }
      // Re-render on the user's turn so the view reflects the turn being answered, not the previous
      // one. The gateway holds the LLM request while lookups run (runtime's session/lookups.py).
      if (event.type === "turn.user") sync(link, call);
      // A claim changes the view (the caller can now see the page) without moving a field.
      if (event.type === "call.claimed") sync(link, call);
    }),
  );
}

async function received(serving: Serving, call: SdkCall, data: unknown, seq: number): Promise<void> {
  const fact = data as { name: string; data: Record<string, unknown>; source: "app" | "participant"; identity?: string };
  const dispatched = inOrder(serving, {
    name: fact.name,
    data: fact.data,
    source: fact.source,
    seq,
    ...(fact.identity === undefined ? {} : { identity: fact.identity }),
  });
  await hooked(call, "onEvent", dispatched, fact.name);
}

async function end(live: Map<string, Live>, call: SdkCall): Promise<void> {
  const link = live.get(call.id);
  if (link === undefined) return;
  live.delete(call.id);
  for (const stop of link.stop) stop();
  link.asking.abandon();
  await hooked(call, "onEnd", runHook(link.agent, "onEnd", hookCall(call)));
  link.unlog();
  setCall(link.agent, null);
  // After every line the hook logged, whether it ran or threw: the gateway seals the call on this word,
  // and a line sent after the seal is refused.
  call.done();
}

// A hook that throws fails its call, never the process: the log names the hook and the error, and the
// call goes on with what the hook had written. For `onEvent`, `event` is the name it was handling.
async function hooked(call: SdkCall, hook: string, running: Promise<unknown>, event?: string): Promise<void> {
  try {
    await running;
  } catch (failed) {
    const error = failed instanceof Error ? failed : new Error(String(failed));
    call.log(HOOK_FAILED, { hook, ...(event === undefined ? {} : { event }), error: error.name, message: error.message });
    console.warn(`pinecall: ${call.id}: ${hook} threw and the call goes on: ${error.message}`);
  }
}

// A view that fails fails its call, never the process: the model keeps the view it had, and the log says why.
function sync(serving: Live, call: SdkCall): void {
  try {
    show(serving, call);
  } catch (failed) {
    const error = failed instanceof Error ? failed : new Error(String(failed));
    call.log(RENDER_FAILED, { error: error.name, message: error.message });
    console.warn(`pinecall: ${call.id} could not render its view and goes on with the one it had: ${error.message}`);
  }
}

// Send only blocks whose text changed. Tools are compared as a whole: only `when` changes them mid-call.
function show(serving: Live, call: SdkCall): void {
  const { blocks } = promptOf(serving.agent);
  for (const block of blocks) {
    if (block.text === (serving.sent.blocks.get(block.name) ?? "")) continue;
    serving.sent.blocks.set(block.name, block.text);
    call.setPrompt(block.name, block.text);
  }
  const asked = serving.asking.open;
  const visible = asked === undefined ? [...serving.agent.visibleTools(), ...serving.transfers] : [asked];
  const key = JSON.stringify(visible);
  if (key !== serving.sent.tools) {
    serving.sent.tools = key;
    call.setTools(visible as unknown as Camel<ToolSpec>[]);
  }
}

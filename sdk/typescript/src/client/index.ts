// @pinecall/agents/client: register agents over the gateway socket, answer tool calls, and read logs.
// Socket layer only, with no dependency on the Agent framework, views or CLI.

export { Agent } from "./agent.js";
export type { AgentGateway, AgentOptions, DevHandler, Tool } from "./agent.js";
export { Call, CallBook } from "./calls.js";
export type { CallGateway, CallStatus } from "./calls.js";
export { Pinecall } from "./client.js";
export type { DrainOptions, Drained, Found, PinecallOptions } from "./client.js";
export { Connection } from "./connection.js";
export type { Backoff, ConnectionHandlers, ConnectionOptions } from "./connection.js";
export { agentLogUrl, appsUrl, callLogUrl, feedUrl, lookupUrl } from "./endpoints.js";
export { DevRefused, PinecallError, Refused, frame, nextId } from "./frames.js";
export { Listeners, camelEvent } from "./listeners.js";
export type { AnyListener, CamelEvent, Listener, Payload } from "./listeners.js";
export { aLostSocket } from "./lost.js";
export { history, observe } from "./observe.js";
export type { LogTarget, Observation, Page, ReadOptions } from "./observe.js";
export { sseFrames } from "./sse.js";
export type { Frame, Streaming } from "./sse.js";
export { signed } from "./signed.js";
export type { World } from "./signed.js";

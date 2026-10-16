// The gateway socket: authentication, reconnect with backoff, and heartbeat pings.

import { decodeEntry } from "../wire/codec.js";
import { type Command, type Entry } from "../wire/envelope.js";
import WebSocket from "ws";
import { appsUrl } from "./endpoints.js";
import { PinecallError } from "./frames.js";
import { asError } from "./listeners.js";
import { signed, type World } from "./signed.js";

/** Reconnect backoff: first delay, cap, and growth factor. */
export interface Backoff {
  firstMs: number;
  capMs: number;
  factor: number;
}

/** Options for a `Connection`. */
export interface ConnectionOptions {
  url: string;
  apiKey: string;
  /** The world to register agents in; omitted means sandbox. See `signed.ts`. */
  env?: World;
  pingMs?: number;
  backoff?: Partial<Backoff>;
}

/** Callbacks a `Connection` drives. */
export interface ConnectionHandlers {
  /** The socket is up; re-send registrations before anything else. */
  onOpen: () => Promise<void>;
  /** One decoded log entry. */
  onEntry: (entry: Entry) => void;
  /** An unreadable frame, a throwing handler, or a socket failure. */
  onError: (error: Error) => void;
  /** Fired every `pingMs` while the socket is up. */
  onHeartbeat: () => void;
}

const DEFAULT_BACKOFF: Backoff = { firstMs: 500, capMs: 30_000, factor: 2 };
const DEFAULT_PING_MS = 30_000;

// RFC 6455 policy violation: the gateway refused the key for this socket. Reported, not retried.
const POLICY_VIOLATION = 1008;

/**
 * One gateway connection across reconnects. The key is sent as `Authorization: Bearer` on the
 * upgrade, never in the URL, which would end up in access logs.
 */
export class Connection {
  #socket: WebSocket | null = null;
  #reconnect: NodeJS.Timeout | null = null;
  #ping: NodeJS.Timeout | null = null;
  #attempt = 0;
  #closed = false;
  #failed: Error | null = null;
  #opened: ((error?: Error) => void) | null = null;
  readonly #backoff: Backoff;
  readonly #pingMs: number;

  constructor(
    private readonly options: ConnectionOptions,
    private readonly handlers: ConnectionHandlers,
  ) {
    this.#backoff = { ...DEFAULT_BACKOFF, ...options.backoff };
    this.#pingMs = options.pingMs ?? DEFAULT_PING_MS;
  }

  /** True while the socket is open. */
  get open(): boolean {
    return this.#socket?.readyState === WebSocket.OPEN;
  }

  /** Open the socket and resolve once `onOpen` has run. Later drops reconnect automatically. */
  async start(): Promise<void> {
    this.#closed = false;
    return new Promise<void>((resolve, reject) => {
      this.#opened = (error) => {
        this.#opened = null;
        if (error) {
          reject(error);
        } else {
          resolve();
        }
      };
      this.#dial();
    });
  }

  /** Send one command. Throws if the socket is down; nothing is queued. */
  send(command: Command): void {
    const socket = this.#socket;
    if (socket === null || socket.readyState !== WebSocket.OPEN) {
      throw new PinecallError(`${command.type}: the gateway is not connected`);
    }
    socket.send(JSON.stringify(command));
  }

  /**
   * Keep the current socket but never reconnect. A reconnect mid-drain would re-register the
   * agents and be handed the calls the drain just moved.
   */
  leaving(): void {
    this.#closed = true;
    if (this.#reconnect !== null) clearTimeout(this.#reconnect);
    this.#reconnect = null;
  }

  /** Close the socket without reconnecting. */
  close(): void {
    this.#closed = true;
    this.#stopTimers();
    this.#socket?.close();
    this.#socket = null;
  }

  #dial(): void {
    const socket = new WebSocket(appsUrl(this.options.url), {
      headers: signed(this.options.apiKey, this.options.env),
    });
    this.#socket = socket;
    socket.on("open", () => void this.#onOpen());
    socket.on("message", (raw: Buffer) => this.#onMessage(raw));
    socket.on("error", (failed: Error) => {
      this.#failed = failed;
      this.handlers.onError(failed);
    });
    socket.on("close", (code: number, reason: Buffer) => this.#onClose(code, reason.toString()));
  }

  async #onOpen(): Promise<void> {
    this.#attempt = 0;
    this.#failed = null;
    try {
      await this.handlers.onOpen();
    } catch (failed) {
      // Report once: as `start`'s rejection on first connect, otherwise through onError.
      if (this.#opened === null) {
        this.handlers.onError(asError(failed));
      } else {
        this.#opened(asError(failed));
      }
      return;
    }
    this.#ping = setInterval(() => this.handlers.onHeartbeat(), this.#pingMs);
    this.#opened?.();
  }

  #onMessage(raw: Buffer): void {
    try {
      this.handlers.onEntry(decodeEntry(JSON.parse(raw.toString()) as unknown));
    } catch (failed) {
      this.handlers.onError(asError(failed));
    }
  }

  #onClose(code: number, reason: string): void {
    this.#stopTimers();
    this.#socket = null;
    if (this.#closed) {
      return;
    }
    // Prefer the close reason: the gateway explains refusals there. Fall back to the code.
    const why = new PinecallError(`the gateway refused the socket: ${this.#failed?.message ?? (reason || `closed with ${code}`)}`);
    // A failed first connect rejects `start`; later closes are retried.
    if (this.#opened !== null) {
      this.#opened(why);
      return;
    }
    // Except a refusal: retrying a key that lacks the scope would loop silently forever.
    if (code === POLICY_VIOLATION) {
      this.#closed = true;
      this.handlers.onError(why);
      return;
    }
    this.#reconnect = setTimeout(() => this.#dial(), this.#waitMs());
  }

  // Full jitter, so clients that lost the same gateway don't reconnect in lockstep.
  #waitMs(): number {
    const window = Math.min(this.#backoff.capMs, this.#backoff.firstMs * this.#backoff.factor ** this.#attempt);
    this.#attempt += 1;
    return Math.random() * window;
  }

  #stopTimers(): void {
    for (const timer of [this.#reconnect, this.#ping]) {
      if (timer !== null) {
        clearTimeout(timer);
      }
    }
    this.#reconnect = null;
    this.#ping = null;
  }
}

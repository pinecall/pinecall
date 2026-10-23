/** A save reloads the agent: its folder watched, a burst of writes settled into one reload, the next copy answering before the one before drains. */

import { type FSWatcher, watch } from "node:fs";
import { extname, sep } from "node:path";

import { errorMessage } from "../errors.js";

// A save is a burst of writes: one reload after it settles.
export const SETTLES_MS = 300;

// What the agent's process, its tools or its package manager write is never a save: a dependency, a
// build, a cache. `test/` is the goldens', which `test --watch` follows.
const NEVER_WATCHED = new Set(["node_modules", ".git", "dist", ".pinecall", "test", "docs", ".venv", "venv", "__pycache__", "vendor", ".bundle"]);

// What an agent is written in: its code, its views, the files its class reads. A log written into the
// folder (`pinecall start >> start.log`) is none, or every line it printed would reload it again.
const WRITTEN_IN = new Set([".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".rb", ".erb", ".py", ".jinja", ".j2", ".json", ".yaml", ".yml", ".md"]);

/** Whether a change to this file, relative to the folder watched, is a save of the agent. */
export function isASave(file: string): boolean {
  return WRITTEN_IN.has(extname(file)) && !file.split(sep).some((part) => NEVER_WATCHED.has(part));
}

/** Call `saved` once each burst of saves under the folders settles; the function returned stops watching. */
export function onSaves(folders: readonly string[], saved: () => void, settlesMs = SETTLES_MS): () => void {
  let timer: NodeJS.Timeout | undefined;
  const watchers: FSWatcher[] = [...new Set(folders)].map((folder) =>
    watch(folder, { recursive: true }, (_event, file) => {
      if (file === null || !isASave(String(file))) return;
      clearTimeout(timer);
      timer = setTimeout(saved, settlesMs);
    }),
  );
  return () => {
    clearTimeout(timer);
    for (const watcher of watchers) watcher.close();
  };
}

/** One copy of the agent: a thread or a process, let go once the next one answers. */
export interface Copy {
  stop(): Promise<unknown>;
}

/** What a reload came to: the version answering now, and the load's own sentence when the save did not load. */
export interface Reloaded {
  version: number;
  broken?: string | undefined;
}

/**
 * A release in miniature, on every save: the next copy registers, then the one before drains. A save
 * that does not load never replaces the copy answering; it says why, and the next save tries again.
 */
export class Releases<T extends Copy> {
  version = 1;
  broken: string | undefined;
  private reloading: Promise<void> = Promise.resolve();
  private closed = false;
  private readonly followers = new Set<(current: T) => void>();

  constructor(
    public current: T,
    private readonly next: () => Promise<T>,
    private readonly told: (reloaded: Reloaded) => void = () => undefined,
  ) {}

  /** Start the next copy, after any reload in flight. */
  reload(): Promise<void> {
    this.reloading = this.reloading.then(() => this.replaced());
    return this.reloading;
  }

  /** Hear every copy that becomes the one answering. */
  onReplaced(listener: (current: T) => void): void {
    this.followers.add(listener);
  }

  /** Resolves once every reload asked so far is over. */
  settled(): Promise<void> {
    return this.reloading;
  }

  /** No reload from now on; a copy that was starting is let go. Resolves once the one in flight is over. */
  async close(): Promise<void> {
    this.closed = true;
    await this.reloading;
  }

  private async replaced(): Promise<void> {
    if (this.closed) return;
    let next: T;
    try {
      next = await this.next();
    } catch (failed) {
      if (this.closed) return;
      this.broken = errorMessage(failed);
      this.told({ version: this.version, broken: this.broken });
      return;
    }
    if (this.closed) {
      await next.stop();
      return;
    }
    const before = this.current;
    this.current = next;
    this.version += 1;
    this.broken = undefined;
    this.told({ version: this.version });
    for (const listener of this.followers) listener(next);
    await before.stop();
  }
}

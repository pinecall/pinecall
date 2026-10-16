/** Open a URL in the platform's default browser, best effort. */

import { spawn } from "node:child_process";

// `start` is a cmd built-in, so Windows goes through cmd; elsewhere xdg-open (freedesktop).
const OPENERS: Record<string, [string, string[]]> = {
  darwin: ["open", []],
  win32: ["cmd", ["/c", "start", ""]],
};
const ELSEWHERE: [string, string[]] = ["xdg-open", []];

/**
 * Try to open the URL in a browser. Failure is ignored: callers always print the URL too, for
 * headless machines (SSH, containers).
 */
export function openInBrowser(url: string, platform: string = process.platform): void {
  const [command, args] = OPENERS[platform] ?? ELSEWHERE;
  try {
    // Detached with output ignored, so browser stderr never interleaves with ours.
    spawn(command, [...args, url], { detached: true, stdio: "ignore" }).unref();
  } catch {
    // No opener installed: the printed URL is enough.
  }
}

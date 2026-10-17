/** The CLI's home folder on this machine: `PINECALL_HOME`, else `~/.pinecall`; where its sign-in and the local runtime's file live. */

import { homedir } from "node:os";
import { join } from "node:path";

/** The variable that moves the home folder away from `~/.pinecall`. */
export const HOME_VARIABLE = "PINECALL_HOME";

/** The home folder: `PINECALL_HOME`, else `~/.pinecall`. */
export function homeOf(env: NodeJS.ProcessEnv): string {
  return env[HOME_VARIABLE] ?? join(homedir(), ".pinecall");
}

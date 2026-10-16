/** Overview doors: list app processes and stop one. */

import { AppListSchema, type AppProcess, AppStoppedSchema } from "@pinecall/core/wire/rest-org";

import { post, read, type Credentials } from "@pinecall/core/api";

/** Connected apps in this world, oldest first. */
export async function readProcesses(credentials: Credentials): Promise<AppProcess[]> {
  return AppListSchema.parse(await read(credentials, "/v1/apps")).apps;
}

/** Close an app socket with the stop code, so the CLI exits instead of reconnecting. */
export async function stopProcess(credentials: Credentials, app: string): Promise<void> {
  AppStoppedSchema.parse(await post(credentials, `/v1/apps/${encodeURIComponent(app)}/stop`, {}));
}

/** The monitors doors: the world's monitors listed, one added, one dropped. */

import { drop, post, read, type Credentials } from "@pinecall/core/api";
import { type Monitor, MonitorListSchema, type MonitorMetric, type MonitorPut, MonitorSchema } from "@pinecall/core/wire/rest-evals";

export type { Monitor, MonitorMetric, MonitorPut };

const PATH = "/v1/monitors";

export async function readMonitors(credentials: Credentials): Promise<Monitor[]> {
  return MonitorListSchema.parse(await read(credentials, PATH)).monitors;
}

/** Watch a number; resolves to the monitor as kept, with its id. */
export async function addMonitor(credentials: Credentials, wanted: MonitorPut): Promise<Monitor> {
  return MonitorSchema.parse(await post(credentials, PATH, wanted));
}

export async function dropMonitor(credentials: Credentials, id: string): Promise<void> {
  await drop(credentials, `${PATH}/${encodeURIComponent(id)}`);
}

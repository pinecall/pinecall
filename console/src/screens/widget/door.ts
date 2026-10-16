/** Widget screen API: widget settings per org, world and agent. */

import { z } from "zod";

import { GatewayError, put, read, type Credentials } from "@pinecall/core/api";

// GET/PUT /v1/agents/{slug}/widget (console-api.md §7). Null means the widget default. The gateway
// only stores these; the copied snippet turns them into attributes.
const SettingsSchema = z.object({
  title: z.string().nullable(),
  tagline: z.string().nullable(),
  greeting: z.string().nullable(),
  accent: z.string().nullable(),
  autostart: z.boolean(),
  // Absent on older gateways; null means auto.
  theme: z.enum(["auto", "light", "dark"]).nullish(),
});
export type WidgetSettings = z.infer<typeof SettingsSchema>;

/** Stored settings for this agent, or null on gateways without them (404). */
export async function readSettings(credentials: Credentials, agent: string): Promise<WidgetSettings | null> {
  try {
    return SettingsSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/widget`));
  } catch (refused) {
    if (refused instanceof GatewayError && refused.status === 404) return null;
    throw refused;
  }
}

/** Replace all settings. */
export async function saveSettings(credentials: Credentials, agent: string, settings: WidgetSettings): Promise<WidgetSettings> {
  return SettingsSchema.parse(await put(credentials, `/v1/agents/${encodeURIComponent(agent)}/widget`, settings));
}

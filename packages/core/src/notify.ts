/** Client for the notifier service: devices, preferences, test notices. */

import { z } from "zod";

import { type Credentials, drop, post, put, read } from "./api";

// The notifier (apps/notify) accepts the same person's key as the gateway; only the base differs.
/** The same credentials pointed at the notifier's base URL. */
export function atTheNotifier(credentials: Credentials, base: string): Credentials {
  return { ...credentials, base };
}

export const DEVICE_PLATFORMS = ["web", "android", "ios"] as const;
export type DevicePlatform = (typeof DEVICE_PLATFORMS)[number];

/** A registered device; the push token is never returned. */
const DeviceRowSchema = z.looseObject({
  id: z.string(),
  platform: z.enum(DEVICE_PLATFORMS),
  kind: z.enum(["alert", "voip"]),
  label: z.string().nullable(),
});

/** Notification preferences and devices for the key's org. */
export const NoticesSchema = z.looseObject({
  org: z.string(),
  org_name: z.string().nullable(),
  events: z.looseObject({ attention: z.boolean(), ringing: z.boolean(), monitors: z.boolean() }),
  devices: z.array(DeviceRowSchema),
});
export type Notices = z.infer<typeof NoticesSchema>;

/** A device to register; for web the token is the PushSubscription JSON. */
export interface ThisDevice {
  platform: DevicePlatform;
  token: string;
  label?: string | null;
}

export interface NoticesChanged {
  events?: { attention?: boolean; ringing?: boolean; monitors?: boolean };
}

export async function readNotices(notifier: Credentials): Promise<Notices> {
  return NoticesSchema.parse(await read(notifier, "/preferences"));
}

export async function saveNotices(notifier: Credentials, changed: NoticesChanged): Promise<Notices> {
  return NoticesSchema.parse(await put(notifier, "/preferences", changed));
}

/** Register a device for the key's org and return its id; idempotent per token. */
export async function registerDevice(notifier: Credentials, device: ThisDevice): Promise<string> {
  return z.looseObject({ id: z.string() }).parse(await post(notifier, "/devices", { kind: "alert", ...device })).id;
}

/** Unregister a device from every org (on sign-out). */
export async function unregisterDevice(notifier: Credentials, device: Omit<ThisDevice, "label">): Promise<void> {
  await drop(notifier, "/devices", { kind: "alert", ...device });
}

/** Forget one of the person's devices by the id the list gave it: a phone lost, a browser no longer used. */
export async function forgetDevice(notifier: Credentials, device: string): Promise<void> {
  await drop(notifier, `/devices/${encodeURIComponent(device)}`);
}

const TestedSchema = z.looseObject({
  sent: z.number(),
  failed: z.array(z.looseObject({ device: z.string(), error: z.string(), dead: z.boolean().default(false) })),
});

/** Send a test notice to the person's devices; returns sent count and failures. */
export async function sendTestNotice(notifier: Credentials): Promise<z.infer<typeof TestedSchema>> {
  return TestedSchema.parse(await post(notifier, "/test", {}));
}

/** VAPID public key for web push, or null when web push is not configured. */
export async function webPushKey(notifier: Credentials): Promise<string | null> {
  return z.looseObject({ publicKey: z.string().nullable() }).parse(await read(notifier, "/vapid")).publicKey;
}

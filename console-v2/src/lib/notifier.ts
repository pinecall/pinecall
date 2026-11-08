/** Web push: notifier URL, service worker, subscription and permission. */

import { atTheNotifier, unregisterDevice } from "@pinecall/core/notify";
import type { Credentials } from "@pinecall/core/api";

// Separate service (apps/notify); override with VITE_PINECALL_NOTIFY. The dev server forwards `/notify`, since the service answers only the console's own origin.
const NOTIFIER: string = (import.meta.env.VITE_PINECALL_NOTIFY as string | undefined) ?? (import.meta.env.DEV ? "/notify" : "https://notify.pinecall.io");

export function theNotifier(credentials: Credentials): Credentials {
  return atTheNotifier(credentials, NOTIFIER);
}

// Served from the root so its scope covers the whole console.
const WORKER = "/sw.js";

// Window event so the top bar's bell updates when the settings screen changes the subscription.
const CHANGED = "pinecall:notices";

export function noticesChanged(): void {
  window.dispatchEvent(new Event(CHANGED));
}

/** Listen for changes and tab focus; returns the unsubscribe function. */
export function onNoticesChanged(listener: () => void): () => void {
  window.addEventListener(CHANGED, listener);
  window.addEventListener("focus", listener);
  return () => {
    window.removeEventListener(CHANGED, listener);
    window.removeEventListener("focus", listener);
  };
}

/** Whether the browser supports service workers, push and notifications. */
export function canBeNotified(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export function permission(): NotificationPermission {
  return canBeNotified() ? Notification.permission : "denied";
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!canBeNotified()) return null;
  const worker = await navigator.serviceWorker.getRegistration(WORKER);
  return (await worker?.pushManager.getSubscription()) ?? null;
}

/** Request permission and subscribe with the notifier's VAPID key; null if denied. */
export async function subscribe(publicKey: string, { anew = false } = {}): Promise<PushSubscription | null> {
  if ((await Notification.requestPermission()) !== "granted") return null;
  const worker = await navigator.serviceWorker.register(WORKER);
  await navigator.serviceWorker.ready;
  const held = await worker.pushManager.getSubscription();
  // After a 410 from the push service, the browser keeps returning the stale subscription until
  // it is unsubscribed.
  if (held !== null && anew) await held.unsubscribe();
  return held !== null && !anew
    ? held
    : worker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytesOf(publicKey) as BufferSource });
}

/** Device token sent to the notifier: the subscription's JSON. */
export function tokenOf(subscription: PushSubscription): string {
  return JSON.stringify(subscription.toJSON());
}

/** Unregister this browser at the notifier and unsubscribe. Best effort: never blocks sign-out. */
export async function forgetThisBrowser(credentials: Credentials): Promise<void> {
  try {
    const subscription = await currentSubscription();
    if (subscription === null) return;
    await unregisterDevice(theNotifier(credentials), { platform: "web", token: tokenOf(subscription) }).catch(() => {});
    await subscription.unsubscribe();
  } catch {
  }
}

/** Device label such as "Chrome on macOS"; keeps no more of the user agent than that. */
export function browserLabel(agent: string = navigator.userAgent): string {
  const browser = /Edg\//.test(agent) ? "Edge" : /Firefox\//.test(agent) ? "Firefox" : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : "A browser";
  const system = /Mac OS X/.test(agent) ? "macOS" : /Windows/.test(agent) ? "Windows" : /Android/.test(agent) ? "Android" : /Linux/.test(agent) ? "Linux" : null;
  return system === null ? browser : `${browser} on ${system}`;
}

// VAPID keys travel as base64url; the push manager takes the bytes.
function bytesOf(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(base64url.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

// Service worker for web push (apps/notify): shows notifications and opens the call on click.
// Deliberately caches nothing and intercepts no requests.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  const notice = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(notice.title || "Pinecall", {
      body: notice.body || "",
      icon: "/pinecall-mark.png",
      // One notification per call; a newer one replaces it and alerts again.
      tag: notice.call || notice.kind || "pinecall",
      renotify: true,
      data: { call: notice.call || null, kind: notice.kind || null, org: notice.org || null, world: notice.world || null },
    }),
  );
});

// Reuse an open console tab if any. `?org=` lets a tab signed into another org switch first
// (lib/from-a-notice.tsx). Both worlds are this one origin's: a notice of the sandbox opens the
// same path under `/sandbox` (lib/mode.ts), production's at the root.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const { call, kind, org, world } = event.notification.data || {};
  const inTheOrg = org ? `?org=${encodeURIComponent(org)}` : "";
  // A monitor that fired has no call to open: its screen is Quality's Monitors.
  const path = call ? `/calls/${encodeURIComponent(call)}${inTheOrg}` : kind === "monitors" ? `/monitors${inTheOrg}` : "/";
  const to = `${self.location.origin}${world === "sandbox" ? "/sandbox" : ""}${path}`;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((open) => {
      const tab = open.find((client) => new URL(client.url).origin === self.location.origin);
      // navigate() fails on tabs this worker doesn't control yet; fall back to a new window.
      if (tab) return tab.focus().then(() => tab.navigate(to)).catch(() => self.clients.openWindow(to));
      return self.clients.openWindow(to);
    }),
  );
});

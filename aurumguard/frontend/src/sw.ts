/// <reference lib="webworker" />
import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { Serwist } from "serwist";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}
declare const self: ServiceWorkerGlobalScope;

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: defaultCache,
});
serwist.addEventListeners();

self.addEventListener("push", (event) => {
  let payload: { title?: string; body?: string; data?: Record<string, unknown>; tag?: string } = {};
  try { payload = event.data ? (event.data.json() as typeof payload) : {}; } catch { payload = { title: "AurumGuard", body: event.data?.text() ?? "" }; }
  const title = payload.title ?? "AurumGuard";
  event.waitUntil(self.registration.showNotification(title, { body: payload.body ?? "", tag: payload.tag, data: payload.data ?? {}, icon: "/icons/icon-192.png", badge: "/icons/icon-192.png" }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string } | undefined)?.url ?? "/notifications";
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});

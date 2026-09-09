import { api } from "./api";

function b64ToUint8(b64: string): Uint8Array {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const s = (b64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(s);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export type PushSupport = "unsupported" | "denied" | "ready" | "subscribed";

export async function pushSupport(): Promise<PushSupport> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator) || !("PushManager" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  return sub ? "subscribed" : "ready";
}

export async function subscribePush(): Promise<{ ok: boolean; message: string }> {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return { ok: false, message: "Push is not supported in this browser. On iOS, install the app to the Home Screen first (iOS 16.4+)." };
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return { ok: false, message: "Notification permission was not granted." };
    const reg = await navigator.serviceWorker.ready;
    const { vapid_public_key } = await api<{ vapid_public_key: string | null; push_provider: string }>("/api/push/vapid-public-key", { auth: false });
    const key = vapid_public_key ?? process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";
    if (!key) return { ok: false, message: "Server has no VAPID key configured (PUSH_PROVIDER=mock). In demo mode notifications appear in the Notification centre only." };
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(key) as BufferSource });
    await api("/api/push/subscribe", { method: "POST", body: { subscription: sub.toJSON(), user_agent: navigator.userAgent } });
    return { ok: true, message: "Push notifications enabled on this device." };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}

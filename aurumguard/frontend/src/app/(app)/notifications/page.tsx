"use client";
import { useEffect, useState } from "react";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Loading, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { pushSupport, subscribePush, type PushSupport } from "@/lib/push";
import type { Notification } from "@/lib/types";

export default function Notifications() {
  const { settings } = useApp();
  const { data, error, refresh } = useApi<{ items: Notification[] }>("/api/notifications?limit=100", 20000);
  const [support, setSupport] = useState<PushSupport>("unsupported"); const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { pushSupport().then(setSupport); }, []);
  async function enable() { const r = await subscribePush(); setMsg(r.message); setSupport(await pushSupport()); }
  async function read(id: string) { await api(`/api/notifications/${id}/read`, { method: "POST" }); refresh(); }
  if (error) return <ErrorBox error={error} />;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Notification centre</h1>
      <Section title="Mobile push">
        <p className="text-sm">Status: <strong>{support}</strong>. Quiet hours {String(settings?.notification_prefs?.quiet_start ?? "23:00")}–{String(settings?.notification_prefs?.quiet_end ?? "07:00")} ({settings?.timezone}); high-priority setups bypass quiet hours by default. Preferences are in Settings.</p>
        <button className="btn btn-primary mt-2" onClick={enable} disabled={support === "unsupported" || support === "denied"}>Enable push on this device</button>
        {msg && <p role="status" className="text-sm mt-1">{msg}</p>}
        <p className="muted text-xs mt-1">iOS: install to the Home Screen first (Share → Add to Home Screen), then enable. Delivery depends on the platform; the centre below is the system of record.</p>
      </Section>
      <Section title="History">{!data ? <Loading /> : data.items.length ? <ul className="space-y-2">{data.items.map((n) => <li key={n.id} className="card" style={{ opacity: n.read_at ? 0.7 : 1 }}><div className="flex justify-between gap-2 flex-wrap"><strong>{n.title}</strong><span className="muted text-xs">{n.created_local} · {n.kind} · {n.priority} · {n.delivery_status}</span></div><pre className="text-sm whitespace-pre-wrap">{n.body}</pre>{n.delivery_detail && <p className="muted text-xs">{n.delivery_detail}</p>}{!n.read_at && <button className="btn py-0 mt-1" onClick={() => read(n.id)}>Mark read</button>}</li>)}</ul> : <p className="muted text-sm">No notifications yet.</p>}</Section>
    </div>
  );
}

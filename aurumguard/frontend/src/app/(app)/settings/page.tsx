"use client";
import { FormEvent, useEffect, useState } from "react";
import { useApp } from "@/components/Providers";
import { Json, Section } from "@/components/ui";
import { api } from "@/lib/api";

const LIMIT_KEYS = ["account_equity", "risk_per_trade_pct", "max_daily_loss_pct", "max_weekly_loss_pct", "max_monthly_drawdown_pct", "max_concurrent_positions", "max_aggregate_open_risk_pct", "max_trades_per_day", "max_consecutive_losses", "max_spread_usd", "max_expected_slippage_usd", "min_net_reward_to_risk"];

export default function Settings() {
  const { settings, reload, me } = useApp();
  const [lim, setLim] = useState<Record<string, string>>({}); const [tz, setTz] = useState(""); const [cutoff, setCutoff] = useState("20:00"); const [autoClose, setAutoClose] = useState(true); const [eventPref, setEventPref] = useState("avoid");
  const [prefs, setPrefs] = useState<Record<string, unknown>>({}); const [msg, setMsg] = useState<string | null>(null); const [mfa, setMfa] = useState<{ secret: string; otpauth: string } | null>(null); const [code, setCode] = useState("");
  useEffect(() => { if (settings) { const l: Record<string, string> = {}; for (const k of LIMIT_KEYS) l[k] = String(settings.risk_limits[k] ?? ""); setLim(l); setTz(settings.timezone); setCutoff(String(settings.risk_limits.friday_cutoff_local ?? "20:00")); setAutoClose(Boolean(settings.risk_limits.friday_auto_close_paper ?? true)); setEventPref(String(settings.risk_limits.event_risk_preference ?? "avoid")); setPrefs(settings.notification_prefs ?? {}); } }, [settings]);
  async function saveLimits(e: FormEvent) { e.preventDefault(); setMsg(null); try { const body: Record<string, unknown> = {}; for (const k of LIMIT_KEYS) if (lim[k] !== "") body[k] = Number(lim[k]); body.friday_cutoff_local = cutoff; body.friday_auto_close_paper = autoClose; body.event_risk_preference = eventPref; await api("/api/users/risk-limits", { method: "PUT", body }); await reload(); setMsg("Risk limits saved (validated within server bounds)."); } catch (ex) { setMsg(ex instanceof Error ? ex.message : String(ex)); } }
  async function savePrefs(e: FormEvent) { e.preventDefault(); setMsg(null); try { await api("/api/users/settings", { method: "PUT", body: { timezone: tz, notification_prefs: prefs } }); await reload(); setMsg("Settings saved."); } catch (ex) { setMsg(ex instanceof Error ? ex.message : String(ex)); } }
  async function weekend(ack: boolean) { try { await api("/api/users/settings", { method: "PUT", body: { weekend_risk_acknowledged: ack } }); await reload(); setMsg(ack ? "Weekend-risk override recorded in the audit log." : "Override removed."); } catch (ex) { setMsg(ex instanceof Error ? ex.message : String(ex)); } }
  if (!settings) return null;
  const bounds = settings.risk_bounds;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Settings</h1>
      {msg && <p role="status" className="card mb-3 text-sm">{msg}</p>}
      <form onSubmit={saveLimits}><Section title="Risk limits (bounds enforced by the server)">
        <div className="grid sm:grid-cols-3 gap-3">{LIMIT_KEYS.map((k) => <label key={k} className="text-sm">{k.replace(/_/g, " ")}{bounds[k] ? <span className="muted"> [{bounds[k][0]}–{bounds[k][1]}]</span> : null}<input className="input" type="number" step="any" value={lim[k] ?? ""} onChange={(e) => setLim({ ...lim, [k]: e.target.value })} /></label>)}
          <label className="text-sm">Friday cutoff (local)<input className="input" type="time" value={cutoff} onChange={(e) => setCutoff(e.target.value)} /></label>
          <label className="text-sm">Event-risk preference<select className="input" value={eventPref} onChange={(e) => setEventPref(e.target.value)}><option value="avoid">avoid</option><option value="reduced">reduced</option><option value="allow_post_confirmation">allow post-confirmation</option></select></label>
          <label className="text-sm flex items-center gap-2 mt-5"><input type="checkbox" checked={autoClose} onChange={(e) => setAutoClose(e.target.checked)} /> Auto-close weekly/swing paper positions at Friday cutoff</label>
        </div>
        <button className="btn btn-primary mt-3">Save risk limits</button>
        <p className="muted text-xs mt-1">Never available: martingale, loss-based scaling, stop widening, limit bypass.</p>
      </Section></form>
      <form onSubmit={savePrefs}><Section title="Timezone and notifications">
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="text-sm">Timezone (IANA)<input className="input" value={tz} onChange={(e) => setTz(e.target.value)} /></label>
          <label className="text-sm">Quiet hours start<input className="input" type="time" value={String(prefs.quiet_start ?? "23:00")} onChange={(e) => setPrefs({ ...prefs, quiet_start: e.target.value })} /></label>
          <label className="text-sm">Quiet hours end<input className="input" type="time" value={String(prefs.quiet_end ?? "07:00")} onChange={(e) => setPrefs({ ...prefs, quiet_end: e.target.value })} /></label>
          <label className="text-sm">Max per hour<input className="input" type="number" value={String(prefs.max_per_hour ?? 12)} onChange={(e) => setPrefs({ ...prefs, max_per_hour: Number(e.target.value) })} /></label>
          <label className="text-sm flex items-center gap-2 mt-5"><input type="checkbox" checked={Boolean(prefs.enabled ?? true)} onChange={(e) => setPrefs({ ...prefs, enabled: e.target.checked })} /> Notifications enabled</label>
          <label className="text-sm flex items-center gap-2 mt-5"><input type="checkbox" checked={Boolean(prefs.quiet_allow_high ?? true)} onChange={(e) => setPrefs({ ...prefs, quiet_allow_high: e.target.checked })} /> High priority bypasses quiet hours</label>
          <label className="text-sm flex items-center gap-2 mt-5"><input type="checkbox" checked={Boolean(prefs.auto_paper_trade ?? false)} onChange={(e) => setPrefs({ ...prefs, auto_paper_trade: e.target.checked })} /> Automatically take confirmed setups in the paper account</label>
        </div>
        <button className="btn btn-primary mt-3">Save</button>
      </Section></form>
      <Section title="Weekend-risk override">
        <p className="text-sm">Status: {settings.weekend_risk_ack_at ? `override active since ${settings.weekend_risk_ack_at}` : "no override (weekly/swing paper positions close at the Friday cutoff)"}</p>
        <div className="flex gap-2 mt-2"><button className="btn" onClick={() => weekend(true)}>I acknowledge weekend gap risk and want positions kept open</button><button className="btn" onClick={() => weekend(false)}>Remove override</button></div>
      </Section>
      <Section title="Multi-factor authentication">
        <p className="text-sm">MFA {me?.mfa_enabled ? "enabled" : "disabled"}.</p>
        {!me?.mfa_enabled && <div className="mt-2"><button className="btn" onClick={async () => setMfa(await api("/api/auth/mfa/setup", { method: "POST" }))}>Start setup</button>{mfa && <div className="mt-2 text-sm"><p>Add this secret to your authenticator: <code>{mfa.secret}</code></p><input className="input" placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value)} /><button className="btn mt-2" onClick={async () => { try { await api("/api/auth/mfa/enable", { method: "POST", body: { code } }); await reload(); setMsg("MFA enabled"); } catch (ex) { setMsg(ex instanceof Error ? ex.message : String(ex)); } }}>Enable</button></div>}</div>}
      </Section>
      <Section title="Current configuration"><Json value={{ contract_spec: settings.contract_spec, horizons_enabled: settings.horizons_enabled, locale: settings.locale }} /></Section>
    </div>
  );
}

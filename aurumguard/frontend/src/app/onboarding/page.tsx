"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/components/Providers";

const TZS = ["Asia/Dubai", "Asia/Riyadh", "Europe/London", "Europe/Berlin", "America/New_York", "Asia/Singapore", "Asia/Tokyo", "UTC"];

export default function Onboarding() {
  const router = useRouter(); const { reload } = useApp();
  const [tz, setTz] = useState("Asia/Dubai"); const [ccy, setCcy] = useState<"USD" | "AED">("USD"); const [equity, setEquity] = useState("10000"); const [risk, setRisk] = useState("0.5"); const [cutoff, setCutoff] = useState("20:00"); const [horizons, setHorizons] = useState<string[]>(["INTRADAY", "SWING", "WEEKLY"]);
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await api("/api/users/onboarding", { method: "POST", body: { timezone: tz, account_currency: ccy, account_equity: Number(equity), risk_per_trade_pct: Number(risk), friday_cutoff_local: cutoff, horizons } }); await reload(); router.replace("/dashboard"); }
    catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)); } finally { setBusy(false); }
  }
  const toggle = (h: string) => setHorizons((x) => x.includes(h) ? x.filter((y) => y !== h) : [...x, h]);
  return (
    <main id="main" className="max-w-lg mx-auto p-6"><h1 className="text-2xl font-bold mb-2">Onboarding</h1><p className="muted mb-4 text-sm">Defaults are conservative and editable later in Settings, within safe bounds enforced by the server.</p>
      <form onSubmit={submit} className="card space-y-3">
        <label className="block text-sm">Timezone<select className="input" value={tz} onChange={(e) => setTz(e.target.value)}>{TZS.map((z) => <option key={z}>{z}</option>)}</select></label>
        <label className="block text-sm">Account currency<select className="input" value={ccy} onChange={(e) => setCcy(e.target.value as "USD" | "AED")}><option>USD</option><option>AED</option></select></label>
        <label className="block text-sm">Paper account equity ({ccy})<input className="input" type="number" min={100} step="100" value={equity} onChange={(e) => setEquity(e.target.value)} /></label>
        <label className="block text-sm">Risk per paper trade (% of equity, 0.1–2.0)<input className="input" type="number" min={0.1} max={2} step={0.1} value={risk} onChange={(e) => setRisk(e.target.value)} /></label>
        <label className="block text-sm">Friday cutoff (local time) for weekly positions<input className="input" type="time" value={cutoff} onChange={(e) => setCutoff(e.target.value)} /></label>
        <fieldset className="text-sm"><legend className="muted">Horizons</legend>{["SCALP", "INTRADAY", "SWING", "WEEKLY"].map((h) => <label key={h} className="me-3"><input type="checkbox" checked={horizons.includes(h)} onChange={() => toggle(h)} /> {h}{h === "SCALP" ? " (no approved strategy; requires tick data)" : ""}</label>)}</fieldset>
        {err && <p role="alert" style={{ color: "var(--sell)" }}>{err}</p>}
        <button className="btn btn-primary" disabled={busy}>Finish</button>
      </form>
    </main>
  );
}

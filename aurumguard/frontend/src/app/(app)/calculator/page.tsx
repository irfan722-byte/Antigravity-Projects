"use client";
import { FormEvent, useState } from "react";
import { Json, Section } from "@/components/ui";
import { api } from "@/lib/api";

export default function Calculator() {
  const [f, setF] = useState({ entry: "2400", stop: "2395", direction: "BUY", spread: "0.3", slippage: "0.2", risk_pct: "", equity: "", tp1: "2410", tp2: "2415" });
  const [res, setRes] = useState<Record<string, unknown> | null>(null); const [err, setErr] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null);
    try { setRes(await api("/api/risk/position-size", { method: "POST", body: { entry: +f.entry, stop: +f.stop, direction: f.direction, spread: +f.spread, slippage: +f.slippage, risk_pct: f.risk_pct ? +f.risk_pct : null, equity: f.equity ? +f.equity : null, tp1: f.tp1 ? +f.tp1 : null, tp2: f.tp2 ? +f.tp2 : null } })); }
    catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)); }
  }
  const field = (k: keyof typeof f, label: string, type = "number") => <label className="block text-sm">{label}<input className="input" type={type} step="any" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Position-size calculator</h1>
      <form onSubmit={submit} className="card grid sm:grid-cols-3 gap-3 mb-4">
        {field("entry", "Intended entry")}{field("stop", "Protective stop")}
        <label className="block text-sm">Direction<select className="input" value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}><option>BUY</option><option>SELL</option></select></label>
        {field("spread", "Spread (USD)")}{field("slippage", "Expected slippage, round trip (USD)")}{field("risk_pct", "Risk % (blank = your setting)")}{field("equity", "Equity USD (blank = your account)")}{field("tp1", "TP1 (optional)")}{field("tp2", "TP2 (optional)")}
        <div className="sm:col-span-3"><button className="btn btn-primary">Calculate</button></div>
      </form>
      {err && <p role="alert" style={{ color: "var(--sell)" }}>{err}</p>}
      {res && <Section title={`Result: ${String(res.status)}`}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm mb-2">
          <div><span className="muted">Lots</span><br /><strong>{String(res.lots)}</strong></div><div><span className="muted">Risk budget</span><br />{String(res.risk_budget_usd)} USD</div><div><span className="muted">Actual risk</span><br />{String(res.risk_usd)} USD ({String(res.risk_pct)}%)</div><div><span className="muted">Effective adverse distance</span><br />{String(res.effective_adverse_distance)}</div>
          <div><span className="muted">Net R:R TP1</span><br />{res.net_rr_tp1 !== null ? Number(res.net_rr_tp1).toFixed(2) : "n/a"}</div><div><span className="muted">Net R:R TP2</span><br />{res.net_rr_tp2 !== null ? Number(res.net_rr_tp2).toFixed(2) : "n/a"}</div>
        </div>
        <p className="text-sm">{String(res.reason)}</p>
        <p className="muted text-xs">{String(res.formula)}</p>
        <Json value={res.cost_breakdown} />
        {!res.contract_spec_verified && <p className="text-sm" style={{ color: "var(--sell)" }}>Contract specification not verified — illustrative only.</p>}
      </Section>}
    </div>
  );
}

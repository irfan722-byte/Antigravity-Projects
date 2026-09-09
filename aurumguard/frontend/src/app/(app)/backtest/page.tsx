"use client";
import { FormEvent, useState } from "react";
import { formatScalar, label, summarize } from "@/components/DataView";
import { useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";

interface Run { run_id: string; strategy_id: string; kind: string; status: string; data_label: string; started_at: string | null; finished_at: string | null; trades_hash: string; error: string | null; summary: Record<string, unknown> }

export default function Backtest() {
  const { data: strats } = useApi<{ strategies: Strategy[] }>("/api/strategies");
  const { data: runs, refresh } = useApi<{ runs: Run[] }>("/api/backtests", 10000);
  const [sel, setSel] = useState<string | null>(null);
  const { data: detail, error: detailErr } = useApi<{ result: Record<string, unknown>; status: string }>(sel ? `/api/backtests/${sel}` : null, 0, [sel]);
  const [f, setF] = useState({ strategy_id: "PBC-H1", start: "2025-09-01T00:00:00+00:00", end: "2025-11-30T00:00:00+00:00", kind: "backtest", spread_multiplier: "1.0", slippage_multiplier: "1.0" });
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: FormEvent) { e.preventDefault(); setErr(null); try { await api("/api/backtests", { method: "POST", body: { ...f, spread_multiplier: +f.spread_multiplier, slippage_multiplier: +f.slippage_multiplier } }); refresh(); } catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)); } }
  const r = detail?.result;
  const m = (r?.metrics ?? r?.out_of_sample ?? {}) as Record<string, unknown>;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Backtesting laboratory</h1>
      <form onSubmit={submit} className="card grid sm:grid-cols-3 gap-3 mb-4">
        <label className="text-sm">Strategy<select className="input" value={f.strategy_id} onChange={(e) => setF({ ...f, strategy_id: e.target.value })}>{(strats?.strategies ?? []).map((s) => <option key={s.id} value={s.id}>{s.id} — {s.name}</option>)}</select></label>
        <label className="text-sm">Kind<select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="backtest">Backtest (single run, score recorded)</option><option value="validation">Validation (walk-forward, MC, costs, thresholds)</option></select></label>
        <label className="text-sm">Start (ISO)<input className="input" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></label>
        <label className="text-sm">End (ISO)<input className="input" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></label>
        <label className="text-sm">Spread ×<input className="input" type="number" step="0.1" value={f.spread_multiplier} onChange={(e) => setF({ ...f, spread_multiplier: e.target.value })} /></label>
        <label className="text-sm">Slippage ×<input className="input" type="number" step="0.1" value={f.slippage_multiplier} onChange={(e) => setF({ ...f, slippage_multiplier: e.target.value })} /></label>
        <div className="sm:col-span-3"><button className="btn btn-primary">Run</button> <span className="muted text-xs">Runs execute in the background. Validation on a year of data takes several minutes.</span></div>
      </form>
      <ErrorBox error={err} />
      <Section title="Runs">{!runs ? <Loading /> : <div className="scroll-x"><table className="table"><thead><tr><th>Run</th><th>Strategy</th><th>Kind</th><th>Data</th><th>Status</th><th>Summary</th><th>Trades hash</th></tr></thead><tbody>{runs.runs.map((x) => <tr key={x.run_id}><td><button className="btn py-0" onClick={() => setSel(x.run_id)}>{x.run_id.slice(0, 8)}</button></td><td>{x.strategy_id}</td><td>{x.kind}</td><td>{x.data_label}</td><td>{x.status}{x.error ? ` (${x.error.slice(0, 60)})` : ""}</td><td className="text-xs">{summarize(x.summary, undefined, 220)}</td><td className="text-xs">{x.trades_hash}</td></tr>)}</tbody></table></div>}</Section>
      {sel && <Section title={`Run ${sel.slice(0, 8)}`}>{detailErr ? <ErrorBox error={detailErr} /> : !detail ? <Loading /> : detail.status !== "DONE" ? <p>{detail.status}</p> : <>
        {"trades" in m && <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm mb-2">{["trades", "win_rate", "expectancy_r", "profit_factor", "max_drawdown_usd", "net_usd", "costs_usd", "brier"].map((k) => <div key={k}><span className="muted">{label(k)}</span><br />{formatScalar(m[k])}</div>)}</div>}
        {r?.acceptance_checklist ? <><h3 className="font-bold text-sm">Acceptance checklist (for human review)</h3><Json value={r.acceptance_checklist} /></> : null}
        {r?.threshold_sensitivity_oos ? <><h3 className="font-bold text-sm">Threshold sensitivity (OOS)</h3><Json value={r.threshold_sensitivity_oos} /></> : null}
        {r?.cost_sensitivity ? <><h3 className="font-bold text-sm">Cost sensitivity</h3><Json value={r.cost_sensitivity} /></> : null}
        {r?.monte_carlo_oos ? <><h3 className="font-bold text-sm">Monte Carlo (OOS)</h3><Json value={r.monte_carlo_oos} /></> : null}
        {r?.walk_forward ? <><h3 className="font-bold text-sm">Walk-forward windows</h3><Json value={r.walk_forward} /></> : null}
        {r?.warnings ? <ul className="text-sm" style={{ color: "var(--sell)" }}>{(r.warnings as string[]).map((w, i) => <li key={i}>{w}</li>)}</ul> : null}
        {(m.equity_curve as { ts: string; equity: number }[] | undefined)?.length ? <details><summary className="text-sm">Equity curve</summary><Json value={m.equity_curve} /></details> : null}
      </>}</Section>}
    </div>
  );
}

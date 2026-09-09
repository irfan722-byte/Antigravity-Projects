"use client";
import { useState } from "react";
import { summarize } from "@/components/DataView";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";

export default function Strategies() {
  const { me } = useApp();
  const { data, error, refresh } = useApi<{ strategies: Strategy[]; note: string }>("/api/strategies", 30000);
  const { data: runs } = useApi<{ runs: { run_id: string; strategy_id: string; kind: string; status: string }[] }>("/api/backtests");
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState(""); const [msg, setMsg] = useState<string | null>(null);
  async function act(id: string, action: string, run_id?: string) {
    try { await api(`/api/strategies/${id}/action`, { method: "POST", body: { action, note, run_id } }); setMsg(`${action} ok`); refresh(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  }
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Strategy registry</h1>
      <p className="muted text-sm mb-3">{data.note}</p>
      {msg && <p role="status" className="text-sm mb-2">{msg}</p>}
      {data.strategies.map((s) => (
        <Section key={s.id} title={`${s.id} · ${s.name} v${s.version}`} right={<span className={`badge ${s.status === "APPROVED" ? "status-BUY_SETUP" : s.status === "SUSPENDED" ? "status-SELL_SETUP" : "status-WAIT"}`}>{s.status}</span>}>
          <p className="text-sm"><strong>Hypothesis:</strong> {s.hypothesis}</p>
          <p className="text-sm"><strong>Horizon:</strong> {s.horizon} · <strong>Timeframes:</strong> {s.timeframes.join(", ")} · <strong>Sessions:</strong> {s.sessions.join(", ")} · <strong>Threshold:</strong> {s.production_threshold ?? "not validated"}</p>
          <p className="text-sm"><strong>Approved regimes:</strong> {s.approved_regimes.join(", ")} · <strong>Prohibited:</strong> {s.prohibited_regimes.join(", ")}</p>
          {s.suspension_reason && <p className="text-sm" style={{ color: "var(--sell)" }}>Suspended: {s.suspension_reason}</p>}
          {s.approval_note && <p className="text-sm muted">Approval note: {s.approval_note}</p>}
          <button className="btn py-1 mt-2" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? "Hide" : "Show"} full strategy card</button>
          {open === s.id && <div className="mt-2 text-sm space-y-2">
            <p><strong>Rationale:</strong> {s.rationale}</p><p><strong>Entry setup:</strong> {s.entry_setup}</p><p><strong>Entry trigger:</strong> {s.entry_trigger}</p><p><strong>Confirmation:</strong> {s.confirmation_rules.join("; ")}</p><p><strong>Invalidation:</strong> {s.invalidation_rules.join("; ")}</p>
            <p><strong>Stop:</strong> {s.stop_methodology}</p><p><strong>TP1:</strong> {s.tp1_methodology}</p><p><strong>TP2:</strong> {s.tp2_methodology}</p><p><strong>Sizing:</strong> {s.sizing_methodology}</p>
            <p><strong>Limits:</strong> min net R:R {s.min_net_rr}, spread ≤ {s.spread_limit}, slippage ≤ {s.slippage_limit}, expiry {s.setup_expiry_minutes} min, max hold {s.max_holding_minutes ?? "n/a"} min · <strong>News:</strong> {s.news_restrictions}</p>
            <p><strong>Known failure regimes:</strong> {s.known_failure_regimes.join("; ")}</p><p><strong>Required data:</strong> {s.required_data.join("; ")}</p>
            <p><strong>Suspension rules:</strong> {summarize(s.suspension_rules, undefined, 400)} · <strong>Retirement:</strong> {s.retirement_rules.join("; ")}</p>
            <details><summary>Parameters</summary><Json value={s.params} /></details>
            <details><summary>Validation results</summary><Json value={s.validation_results} /></details>
            <details><summary>Backtest results (summary)</summary><Json value={{ in_sample: (s.backtest_results as { in_sample?: unknown }).in_sample, out_of_sample: (s.backtest_results as { out_of_sample?: unknown }).out_of_sample, acceptance_checklist: (s.backtest_results as { acceptance_checklist?: unknown }).acceptance_checklist }} /></details>
            <details><summary>Approval history</summary><Json value={s.approval_history} /></details>
            <details><summary>Change log</summary><Json value={s.change_log} /></details>
            {me?.role === "admin" && <div className="card space-y-2"><h3 className="font-bold">Admin actions (human approval workflow)</h3>
              <label className="block">Note (required, ≥10 chars)<input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></label>
              <div className="flex gap-2 flex-wrap">
                <select className="input w-auto" onChange={(e) => { if (e.target.value) act(s.id, "record_validation", e.target.value); }}><option value="">Record validation from run…</option>{(runs?.runs ?? []).filter((r) => r.strategy_id === s.id && r.kind === "validation" && r.status === "DONE").map((r) => <option key={r.run_id} value={r.run_id}>{r.run_id.slice(0, 8)}</option>)}</select>
                <button className="btn" onClick={() => act(s.id, "approve")}>Approve</button><button className="btn" onClick={() => act(s.id, "suspend")}>Suspend</button><button className="btn" onClick={() => act(s.id, "reactivate")}>Reactivate</button><button className="btn" onClick={() => act(s.id, "retire")}>Retire</button>
              </div></div>}
          </div>}
        </Section>
      ))}
    </div>
  );
}

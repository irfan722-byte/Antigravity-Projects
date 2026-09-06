"use client";
import { useState } from "react";
import Link from "next/link";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Loading, Section } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtNum, fmtTime } from "@/lib/format";

interface Pos { position_id: string; decision_id: string | null; strategy_id: string; horizon: string; direction: string; status: string; lots_initial: number; lots_open: number; entry_price: number; entry_ts: string; exit_ts: string | null; stop: number; tp1: number; tp2: number; realised_pnl_usd: number; exit_reason: string | null; r_multiple: number | null; tp1_hit: boolean; fills: { ts: string; price: number; lots: number; kind: string; label: string }[] }
interface Data { open: Pos[]; closed: Pos[]; pending_orders: { order_id: string; direction: string; lots: number; status: string; reject_reason: string | null }[]; realised_usd: number; unrealised_usd: number | null; open_risk_usd: number; demo_data: boolean }

export default function Paper() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error, refresh } = useApi<Data>("/api/paper/positions", 20000);
  const [msg, setMsg] = useState<string | null>(null);
  async function close(id: string) {
    try { await api("/api/paper/close", { method: "POST", body: { position_id: id, reason: "manual" } }); setMsg(`Closed ${id}`); refresh(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  }
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const row = (p: Pos) => <tr key={p.position_id}><td>{p.position_id}</td><td>{p.strategy_id} · {p.horizon}</td><td>{p.direction}</td><td>{p.lots_open}/{p.lots_initial}</td><td>{fmtNum(p.entry_price)}<br /><span className="muted text-xs">{fmtTime(p.entry_ts, tz)}</span></td><td>{fmtNum(p.stop)}</td><td>{fmtNum(p.tp1)}{p.tp1_hit ? " ✓" : ""}</td><td>{fmtNum(p.tp2)}</td><td>{fmtNum(p.realised_pnl_usd)}{p.r_multiple !== null ? ` (${p.r_multiple.toFixed(2)}R)` : ""}</td><td>{p.exit_reason ?? "open"} {p.fills.some((f) => f.label) ? <span className="muted text-xs">{p.fills.map((f) => f.label).filter(Boolean).join(" ")}</span> : null}</td><td>{p.status === "OPEN" ? <button className="btn py-1" onClick={() => close(p.position_id)}>Close</button> : p.decision_id ? <Link href={`/setups/${p.decision_id}`}>setup</Link> : null}</td></tr>;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Paper-trading workspace</h1>
      {data.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA</p>}
      <div className="grid grid-cols-3 gap-3 mb-3"><div className="kpi card"><span className="label">Realised</span><span className="value">{fmtNum(data.realised_usd)} USD</span></div><div className="kpi card"><span className="label">Unrealised</span><span className="value">{data.unrealised_usd === null ? "n/a" : fmtNum(data.unrealised_usd)} USD</span></div><div className="kpi card"><span className="label">Open risk</span><span className="value">{fmtNum(data.open_risk_usd)} USD</span></div></div>
      {msg && <p role="status" className="text-sm mb-2">{msg}</p>}
      <Section title="Open positions">{data.open.length ? <div className="scroll-x"><table className="table"><thead><tr><th>ID</th><th>Strategy</th><th>Dir</th><th>Lots</th><th>Entry</th><th>Stop</th><th>TP1</th><th>TP2</th><th>P&amp;L</th><th>Exit</th><th></th></tr></thead><tbody>{data.open.map(row)}</tbody></table></div> : <p className="muted text-sm">No open paper positions. Take a setup from the signal feed, or enable auto paper entry in Settings.</p>}</Section>
      <Section title="Pending / rejected orders">{data.pending_orders.length ? <ul className="text-sm">{data.pending_orders.map((o) => <li key={o.order_id}>{o.order_id} {o.direction} {o.lots} lots — {o.status}{o.reject_reason ? `: ${o.reject_reason}` : ""}</li>)}</ul> : <p className="muted text-sm">none</p>}</Section>
      <Section title="Closed positions (latest 100)" right={<Link href="/journal" className="text-sm">Full journal</Link>}>{data.closed.length ? <div className="scroll-x"><table className="table"><thead><tr><th>ID</th><th>Strategy</th><th>Dir</th><th>Lots</th><th>Entry</th><th>Stop</th><th>TP1</th><th>TP2</th><th>P&amp;L</th><th>Exit</th><th></th></tr></thead><tbody>{[...data.closed].reverse().map(row)}</tbody></table></div> : <p className="muted text-sm">none yet</p>}</Section>
      <p className="muted text-xs">Fills use bid/ask, slippage and conservative same-bar assumptions (labelled). Stops are never widened. Live execution is disabled.</p>
    </div>
  );
}

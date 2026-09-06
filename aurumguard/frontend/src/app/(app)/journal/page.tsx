"use client";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Loading, Section } from "@/components/ui";
import { fmtNum, fmtTime } from "@/lib/format";

interface Trade { trade_id: string; strategy_id: string; horizon: string; direction: string; entry_ts: string; exit_ts: string; entry_price: number; exit_price: number; lots: number; risk_usd: number; pnl_usd: number; costs_usd: number; exit_reason: string; session: string; regime: string; score: number | null; near_event: boolean; label: string; r: number }
interface Ev { ts: string; kind: string; ref_id: string; detail: Record<string, unknown> }

export default function Journal() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<{ trades: Trade[]; events: Ev[] }>("/api/paper/journal", 60000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const base = (process.env.NEXT_PUBLIC_API_URL ?? "");
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Trade journal</h1>
      <p className="text-sm mb-3"><a className="btn" href={`${base}/api/paper/export.csv`} target="_blank" rel="noreferrer">Export CSV</a> <span className="muted">(requires a logged-in session; use the Privacy page export for a full JSON dump)</span></p>
      <Section title="Closed paper trades">{data.trades.length ? <div className="scroll-x"><table className="table"><thead><tr><th>ID</th><th>Strategy</th><th>Dir</th><th>Entry</th><th>Exit</th><th>Lots</th><th>Risk</th><th>P&amp;L</th><th>R</th><th>Costs</th><th>Reason</th><th>Session</th><th>Regime</th><th>Score</th><th>Labels</th></tr></thead><tbody>
        {data.trades.map((t) => <tr key={t.trade_id}><td>{t.trade_id}</td><td>{t.strategy_id}<br /><span className="muted text-xs">{t.horizon}</span></td><td>{t.direction}</td><td>{fmtNum(t.entry_price)}<br /><span className="muted text-xs">{fmtTime(t.entry_ts, tz)}</span></td><td>{fmtNum(t.exit_price)}<br /><span className="muted text-xs">{fmtTime(t.exit_ts, tz)}</span></td><td>{t.lots}</td><td>{fmtNum(t.risk_usd)}</td><td>{fmtNum(t.pnl_usd)}</td><td>{t.r.toFixed(2)}</td><td>{fmtNum(t.costs_usd)}</td><td>{t.exit_reason}</td><td>{t.session}</td><td>{t.regime}</td><td>{t.score ?? "–"}</td><td>{t.label}{t.near_event ? " NEAR_EVENT" : ""}</td></tr>)}
      </tbody></table></div> : <p className="muted text-sm">No closed paper trades yet.</p>}</Section>
      <Section title="Event log (latest 200)"><div className="scroll-x"><table className="table"><thead><tr><th>Time</th><th>Kind</th><th>Ref</th><th>Detail</th></tr></thead><tbody>{data.events.map((e, i) => <tr key={i}><td>{fmtTime(e.ts, tz)}</td><td>{e.kind}</td><td>{e.ref_id}</td><td className="text-xs">{JSON.stringify(e.detail)}</td></tr>)}</tbody></table></div></Section>
    </div>
  );
}

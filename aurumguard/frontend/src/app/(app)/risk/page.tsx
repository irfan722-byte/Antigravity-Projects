"use client";
import Link from "next/link";
import { useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { fmtNum } from "@/lib/format";

interface Risk { limits: Record<string, number | string | boolean>; account: Record<string, number | { position_id: string; strategy_id: string; horizon: string; direction: string; risk_usd: number }[]>; locks: Record<string, boolean | Record<string, string>>; contract_spec: Record<string, unknown> }

export default function RiskPage() {
  const { data, error } = useApi<Risk>("/api/risk/status", 30000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const a = data.account as Record<string, number>;
  const lim = data.limits as Record<string, number>;
  const lockKeys = Object.entries(data.locks).filter(([k]) => k.endsWith("_locked")) as [string, boolean][];
  const bar = (used: number, limit: number) => <div aria-hidden style={{ background: "var(--border)", borderRadius: 6, height: 8 }}><div style={{ width: `${Math.min(100, Math.abs(used) / limit * 100)}%`, background: Math.abs(used) >= limit ? "var(--sell)" : "var(--accent)", height: 8, borderRadius: 6 }} /></div>;
  const eq = a.starting_equity_usd;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Risk dashboard</h1>
      <div className="grid md:grid-cols-2 gap-3">
        <Section title="Budgets (USD)">
          <div className="space-y-3 text-sm">
            <div>Daily loss: {fmtNum(a.realised_today_usd)} of −{fmtNum(eq * lim.max_daily_loss_pct / 100)} {bar(Math.min(0, a.realised_today_usd), eq * lim.max_daily_loss_pct / 100)}</div>
            <div>Weekly loss: {fmtNum(a.realised_week_usd)} of −{fmtNum(eq * lim.max_weekly_loss_pct / 100)} {bar(Math.min(0, a.realised_week_usd), eq * lim.max_weekly_loss_pct / 100)}</div>
            <div>Aggregate open risk: {fmtNum(a.aggregate_open_risk_usd)} of {fmtNum(eq * lim.max_aggregate_open_risk_pct / 100)} {bar(a.aggregate_open_risk_usd, eq * lim.max_aggregate_open_risk_pct / 100)}</div>
            <div>Month drawdown from peak: {fmtNum((a.month_peak_equity_usd - a.equity_usd) / a.month_peak_equity_usd * 100, 2)}% of {lim.max_monthly_drawdown_pct}%</div>
            <div>Trades today: {a.trades_today} / {lim.max_trades_per_day} · consecutive losses: {a.consecutive_losses} / {lim.max_consecutive_losses} · open positions: {a.open_positions} / {lim.max_concurrent_positions}</div>
          </div>
        </Section>
        <Section title="Lock status">
          <ul className="text-sm">{lockKeys.map(([k, v]) => <li key={k}><span aria-hidden>{v ? "🔒" : "✓"}</span> {k.replace("_locked", "")}: <strong>{v ? "LOCKED" : "clear"}</strong></li>)}</ul>
          <Json value={(data.locks as { details: Record<string, string> }).details} />
          <p className="muted text-xs">Locks are enforced server-side on every setup and every paper order. They cannot be bypassed from the UI.</p>
        </Section>
      </div>
      <Section title="Configured limits" right={<Link href="/settings" className="text-sm">Edit in Settings</Link>}><Json value={data.limits} /></Section>
      <Section title="Contract specification in use"><Json value={data.contract_spec} /><p className="text-sm" style={{ color: "var(--sell)" }}>{data.contract_spec.verified ? "" : "This specification is NOT verified against a broker document. Sizing is illustrative until a verified specification is configured."}</p></Section>
    </div>
  );
}

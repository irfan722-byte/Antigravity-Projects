"use client";
import Link from "next/link";
import { useApp, useApi } from "@/components/Providers";
import { DecisionCard, ErrorBox, Kpi, Loading, Section, StatusBadge } from "@/components/ui";
import { countdown, fmtNum, fmtTime } from "@/lib/format";
import type { CalendarEvent, Decision, Quote } from "@/lib/types";

interface Risk { limits: Record<string, number>; account: { equity_usd: number; realised_today_usd: number; realised_week_usd: number; aggregate_open_risk_usd: number; aggregate_open_risk_pct: number | null; open_positions: number }; locks: Record<string, boolean | Record<string, string>> }
interface Health { providers: { name: string; kind: string; ok: boolean; is_mock: boolean }[] }
interface Perf { strategies: { id: string; status: string; paper: { trades?: number; expectancy_r?: number; win_rate?: number }; out_of_sample: { trades?: number; expectancy_r?: number } }[] }

export default function Dashboard() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data: q } = useApi<Quote>("/api/market/quote", 15000);
  const { data: dec, error: e1 } = useApi<{ horizons: Record<string, Decision | null> }>("/api/decisions/latest", 30000);
  const { data: risk } = useApi<Risk>("/api/risk/status", 30000);
  const { data: cal } = useApi<{ events: CalendarEvent[] }>("/api/calendar?days_back=0&days_ahead=7", 60000);
  const { data: health } = useApi<Health>("/api/market/health", 60000);
  const { data: reg } = useApi<{ regime: { primary: string; confidence: number; tags: string[] } | null }>("/api/regime", 60000);
  const { data: feed } = useApi<{ items: Decision[] }>("/api/decisions/feed?limit=8", 30000);
  const { data: perf } = useApi<Perf>("/api/performance/strategies", 120000);
  const next = cal?.events.filter((e) => e.importance === "HIGH" && new Date(e.scheduled_ts).getTime() > Date.now())[0];
  const setups = feed?.items.filter((d) => d.setup) ?? [];
  const locks = risk ? Object.entries(risk.locks).filter(([k, v]) => k.endsWith("_locked") && v === true).map(([k]) => k.replace("_locked", "")) : [];
  const badProviders = health?.providers.filter((p) => !p.ok) ?? [];
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">XAU/USD dashboard</h1>
      <ErrorBox error={e1} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Kpi label="Bid / Ask" value={q ? `${fmtNum(q.bid)} / ${fmtNum(q.ask)}` : "…"} sub={q ? `spread ${fmtNum(q.spread)} · ${fmtTime(q.ts, tz, "en", false)}` : ""} />
        <Kpi label="Market / session" value={q?.market_state ?? "…"} sub={q?.session} />
        <Kpi label="Next major USD event" value={next ? countdown(next.scheduled_ts) : "none in 7d"} sub={next ? `${next.name} · ${fmtTime(next.scheduled_ts, tz)}` : ""} />
        <Kpi label="Regime" value={reg?.regime?.primary ?? "n/a"} sub={reg?.regime ? `conf ${Math.round(reg.regime.confidence * 100)}% ${reg.regime.tags.join(" ")}` : ""} />
      </div>
      <Section title="Decisions by horizon">
        {!dec ? <Loading /> : <div className="grid md:grid-cols-2 gap-3">{["SCALP", "INTRADAY", "SWING", "WEEKLY"].map((h) => <DecisionCard key={h} d={dec.horizons[h]} tz={tz} compact />)}</div>}
      </Section>
      <div className="grid md:grid-cols-2 gap-3">
        <Section title="Risk">
          {risk ? <div className="grid grid-cols-2 gap-2 text-sm">
            <div><span className="muted">Equity</span><br />{fmtNum(risk.account.equity_usd)} USD</div>
            <div><span className="muted">Aggregate open risk</span><br />{fmtNum(risk.account.aggregate_open_risk_usd)} USD ({fmtNum(risk.account.aggregate_open_risk_pct, 2)}%)</div>
            <div><span className="muted">Today</span><br />{fmtNum(risk.account.realised_today_usd)} USD</div>
            <div><span className="muted">This week</span><br />{fmtNum(risk.account.realised_week_usd)} USD</div>
            <div><span className="muted">Open paper positions</span><br />{risk.account.open_positions}</div>
            <div><span className="muted">Risk locks</span><br />{locks.length ? <strong style={{ color: "var(--sell)" }}>{locks.join(", ")}</strong> : "none"}</div>
          </div> : <Loading />}
          <Link href="/risk" className="text-sm">Risk dashboard</Link>
        </Section>
        <Section title="Data health">
          {health ? <p className="text-sm">{badProviders.length ? <span style={{ color: "var(--sell)" }}>Degraded: {badProviders.map((p) => `${p.kind}:${p.name}`).join(", ")}</span> : "All providers healthy"}{health.providers.some((p) => p.is_mock) ? " · mock providers active (DEMO)" : ""}</p> : <Loading />}
          {q?.integrity?.issues?.length ? <ul className="text-xs muted">{q.integrity.issues.map((i) => <li key={i.code}>{i.severity} {i.code}: {i.message}</li>)}</ul> : null}
          <Link href="/data-health" className="text-sm">Provider health</Link>
        </Section>
      </div>
      <Section title="Latest actionable and recent setups">
        {setups.length ? <ul className="text-sm space-y-1">{setups.map((d) => <li key={d.decision_id} className="flex gap-2 items-center flex-wrap"><StatusBadge status={d.status} /><span>{d.horizon} · {d.strategy_id}</span><span className="muted">{fmtTime(d.as_of, tz)}</span><Link href={`/setups/${d.decision_id}`}>details</Link></li>)}</ul> : <p className="muted text-sm">No setups issued recently. NO TRADE and WAIT are normal outcomes.</p>}
      </Section>
      <Section title="Strategy performance summary">
        {perf ? <div className="scroll-x"><table className="table"><thead><tr><th>Strategy</th><th>Status</th><th>OOS trades</th><th>OOS expectancy (R)</th><th>Paper trades</th><th>Paper expectancy (R)</th></tr></thead><tbody>{perf.strategies.map((s) => <tr key={s.id}><td>{s.id}</td><td>{s.status}</td><td>{s.out_of_sample.trades ?? "–"}</td><td>{s.out_of_sample.expectancy_r ?? "–"}</td><td>{s.paper.trades ?? 0}</td><td>{s.paper.expectancy_r ?? "–"}</td></tr>)}</tbody></table></div> : <Loading />}
        <p className="muted text-xs mt-1">Backtest and paper samples are shown separately and never combined.</p>
      </Section>
    </div>
  );
}

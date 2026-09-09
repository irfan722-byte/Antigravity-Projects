"use client";
import { use, useState } from "react";
import Link from "next/link";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, EvidenceList, Loading, Section, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtNum, fmtTime } from "@/lib/format";
import type { Decision } from "@/lib/types";

export default function SetupDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data: d, error } = useApi<Decision>(`/api/decisions/${id}`);
  const [msg, setMsg] = useState<string | null>(null);
  if (error) return <ErrorBox error={error} />;
  if (!d) return <Loading />;
  const s = d.setup;
  async function paper() {
    try { const r = await api<{ status: string; reject_reason: string | null; lots: number }>("/api/paper/orders", { method: "POST", body: { decision_id: id } }); setMsg(`Paper order ${r.status} (${r.lots} lots)${r.reject_reason ? ": " + r.reject_reason : ""}`); }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  }
  return (
    <div>
      <div className="flex items-center gap-2 mb-2 flex-wrap"><h1 className="text-2xl font-bold">Setup {d.horizon}</h1><StatusBadge status={d.status} /><span className="muted text-sm">{fmtTime(d.as_of, tz)}</span></div>
      {d.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA</p>}
      <p className="mb-3">{d.reason}</p>
      {s ? (<>
        <Section title="Mandatory setup content">
          <div className="scroll-x"><table className="table"><tbody>
            {[
              ["Instrument", s.instrument], ["Bid / Ask / Spread", `${fmtNum(s.bid)} / ${fmtNum(s.ask)} / ${fmtNum(s.spread)}`], ["Data provider", s.data_provider], ["Price timestamp", fmtTime(s.price_timestamp, tz)], ["User timezone", s.user_timezone], ["Horizon", s.horizon], ["Strategy", `${s.strategy_name} (${s.strategy_id}) v${s.strategy_version}`], ["Direction", s.direction],
              ["Entry trigger", s.entry_trigger], ["Entry zone", `${fmtNum(s.entry_zone_low)} – ${fmtNum(s.entry_zone_high)} (reference ${fmtNum(s.entry_reference)})`], ["Entry confirmation", s.entry_confirmation_required ? (s.entry_confirmed ? "required and confirmed" : "STILL REQUIRED") : "not required"],
              ["Protective stop", `${fmtNum(s.stop_loss)} — ${s.stop_rationale}`], ...s.targets.map((t) => [t.label, `${fmtNum(t.price)} · net R:R ${fmtNum(t.net_reward_to_risk)} · ${t.rationale}`]),
              ["Estimated spread / slippage", `${fmtNum(s.estimated_spread)} / ${fmtNum(s.estimated_slippage)}`], ["Estimated fees / financing", `${fmtNum(s.estimated_fees_usd)} / ${fmtNum(s.estimated_financing_usd)} USD`], ["Setup expiry", fmtTime(s.expiry, tz)], ["Max holding until", fmtTime(s.max_holding_until, tz)],
              ["Market regime", `${(s.market_regime as { primary?: string }).primary} (conf ${(s.market_regime as { confidence?: number }).confidence})`], ["News risk", `${(s.news_risk as { phase?: string }).phase}${(s.news_risk as { event?: { name?: string } }).event?.name ? " · " + (s.news_risk as { event?: { name?: string } }).event?.name : ""}`],
              ["Position size", `${String((s.position_size as { lots?: number }).lots)} lots (${(s.position_size as { status?: string }).status}) — ${(s.position_size as { reason?: string }).reason}`], ["Total account risk", `${fmtNum(s.total_account_risk_usd)} USD (${fmtNum(s.total_account_risk_pct, 3)}%)`], ["Aggregate exposure after", `${fmtNum(s.aggregate_exposure_after_usd)} USD (${fmtNum(s.aggregate_exposure_after_pct, 3)}%)`],
              ["Confidence (calibrated range)", `${Math.round(s.confidence_low * 100)}% – ${Math.round(s.confidence_high * 100)}% via ${s.confidence_method}`], ["Historical comparable sample", String(s.historical_sample_size)], ["Backtest approval status", s.backtest_approval_status], ["Data quality", s.data_quality_status], ["Notification timestamp", fmtTime(s.notification_timestamp, tz)], ["Contract spec", s.contract_spec_id],
            ].map(([k, v]) => <tr key={k as string}><th>{k as string}</th><td>{v as string}</td></tr>)}
          </tbody></table></div>
        </Section>
        <Section title="Supporting evidence"><EvidenceList items={s.supporting_evidence} /></Section>
        <Section title="Contradictory evidence"><EvidenceList items={s.contradictory_evidence} /></Section>
        <Section title="Invalidation conditions"><ul className="text-sm list-disc ps-5">{s.invalidation_conditions.map((x, i) => <li key={i}>{x}</li>)}</ul></Section>
        <p className="card text-sm mb-3" role="note">{s.uncertainty_statement}</p>
        <div className="flex gap-3 items-center flex-wrap"><button className="btn btn-primary" onClick={paper}>Take in paper account</button><Link href={`/evidence/${id}`} className="btn">Evidence Inspector</Link>{msg && <span role="status" className="text-sm">{msg}</span>}</div>
        <p className="muted text-xs mt-2">Paper entry re-runs all risk limits on the server. Live execution is disabled.</p>
      </>) : <Section title="No setup"><p className="text-sm">This decision did not produce a setup. See the <Link href={`/evidence/${id}`}>Evidence Inspector</Link> for the gates and rules that were not met.</p></Section>}
    </div>
  );
}

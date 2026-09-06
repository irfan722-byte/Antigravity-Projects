"use client";
import { use } from "react";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { fmtTime } from "@/lib/format";
import type { CalendarEvent } from "@/lib/types";

interface Detail { event: CalendarEvent; scenarios: Record<string, unknown>[]; reaction: Record<string, unknown> | null; news_phase: string; config: Record<string, unknown>; demo_data: boolean }

export default function EventDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<Detail>(`/api/calendar/${id}`, 60000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const e = data.event;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">{e.name}</h1>
      <p className="muted mb-3">{fmtTime(e.scheduled_ts, tz)} · {e.importance} · {e.category} · verification {e.verification} · phase now: <strong>{data.news_phase}</strong></p>
      {data.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA</p>}
      <Section title="Values"><div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-sm"><div><span className="muted">Actual</span><br />{e.actual ?? "not released"}</div><div><span className="muted">Consensus</span><br />{e.consensus ?? "–"}</div><div><span className="muted">Prior</span><br />{e.prior ?? "–"}</div><div><span className="muted">Revised prior</span><br />{e.revised_prior ?? "–"}</div><div><span className="muted">Std. surprise</span><br />{e.standardised_surprise ?? "n/a"}</div></div></Section>
      <Section title="Pre-event scenario analysis (not a prediction)">
        <div className="scroll-x"><table className="table"><thead><tr><th>Scenario</th><th>Interpretation</th><th>Gold median move 30m</th><th>IQR</th><th>Reversal rate 2h</th><th>n</th></tr></thead><tbody>
          {data.scenarios.filter((s) => s.scenario).map((s) => { const h = (s.history ?? {}) as Record<string, number | null>; return <tr key={String(s.scenario)}><td>{String(s.scenario)}</td><td>{String(s.interpretation)}</td><td>{h.gold_median_move_30m ?? "n/a"}</td><td>{h.gold_iqr_30m ?? "n/a"}</td><td>{h.reversal_rate_2h ?? "n/a"}</td><td>{h.sample_size ?? 0}</td></tr>; })}
        </tbody></table></div>
        <p className="muted text-xs mt-1">History: {String((data.scenarios.find((s) => s.total_history_sample) ?? {}).history_source ?? "unavailable")}, sample {String((data.scenarios.find((s) => s.total_history_sample) ?? {}).total_history_sample ?? 0)}. Spreads and slippage usually widen into the release.</p>
      </Section>
      <Section title="Post-release reaction (verified data only)">{data.reaction ? <Json value={data.reaction} /> : <p className="muted text-sm">No verified reaction yet for this event.</p>}</Section>
      <Section title="State machine configuration"><Json value={data.config} /></Section>
    </div>
  );
}

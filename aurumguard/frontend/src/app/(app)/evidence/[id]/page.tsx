"use client";
import { use } from "react";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, EvidenceList, GateList, Json, Loading, Section, StatusBadge } from "@/components/ui";
import { fmtTime } from "@/lib/format";
import type { Decision, EvidenceItem, Gate } from "@/lib/types";

export default function Evidence({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data: d, error } = useApi<Decision>(`/api/decisions/${id}`);
  if (error) return <ErrorBox error={error} />;
  if (!d) return <Loading />;
  const ev = (d.evidence_inspector ?? {}) as Record<string, unknown>;
  const list = (k: string) => (ev[k] as string[] | undefined) ?? [];
  return (
    <div>
      <div className="flex items-center gap-2 mb-2 flex-wrap"><h1 className="text-2xl font-bold">Evidence Inspector</h1><StatusBadge status={d.status} /><span className="muted text-sm">{d.horizon} · {fmtTime(d.as_of, tz)}</span></div>
      <p className="text-sm mb-3">{d.reason}</p>
      <div className="grid md:grid-cols-2 gap-3">
        <Section title="1. Data used"><ul className="text-sm">{list("data_used").map((x, i) => <li key={i}>{x}</li>)}</ul></Section>
        <Section title="2–3. Data unavailable / excluded"><ul className="text-sm">{[...list("data_unavailable"), ...list("data_excluded")].map((x, i) => <li key={i}>{x}</li>) || <li>none</li>}</ul>{!list("data_unavailable").length && <p className="muted text-sm">none</p>}</Section>
        <Section title="4–5. Sources and timestamps"><Json value={{ sources: ev.data_sources, timestamps: ev.timestamps }} /></Section>
        <Section title="6. Feature values"><Json value={ev.feature_values} /></Section>
        <Section title="7. Strategy rules triggered"><ul className="text-sm">{list("rules_triggered").map((x, i) => <li key={i}>✓ {x}</li>)}</ul>{!list("rules_triggered").length && <p className="muted text-sm">none</p>}</Section>
        <Section title="8. Rules not triggered"><ul className="text-sm">{list("rules_not_triggered").map((x, i) => <li key={i}>✗ {x}</li>)}</ul>{!list("rules_not_triggered").length && <p className="muted text-sm">none</p>}</Section>
        <Section title="9. Hard gates passed"><GateList gates={(ev.gates_passed as Gate[]) ?? []} /></Section>
        <Section title="10. Hard gates failed"><GateList gates={(ev.gates_failed as Gate[]) ?? []} /></Section>
        <Section title="11. Supporting evidence"><EvidenceList items={(ev.supporting as EvidenceItem[]) ?? []} /></Section>
        <Section title="12. Contradictory evidence"><EvidenceList items={(ev.contradictory as EvidenceItem[]) ?? []} /></Section>
        <Section title="13. Market regime"><Json value={ev.regime} /></Section>
        <Section title="14–17. Versions"><Json value={{ model_version: ev.model_version, strategy_version: ev.strategy_version, scoring_config: ev.scoring_config, calibration_version: ev.calibration_version, score: ev.score, threshold: ev.threshold, calibration: ev.calibration }} /></Section>
        <Section title="18. Risk calculations"><Json value={ev.risk_calculations} /></Section>
        <Section title="19. Known limitations"><ul className="text-sm list-disc ps-5">{list("known_limitations").map((x, i) => <li key={i}>{x}</li>)}</ul></Section>
        <Section title="20. Immutable decision timestamp"><p className="text-sm">{String(ev.decision_timestamp)} (UTC) · {fmtTime(String(ev.decision_timestamp), tz)}</p></Section>
        <Section title="21. Outcome (recorded separately after expiry)">{d.outcome ? <Json value={d.outcome} /> : <p className="muted text-sm">Not yet evaluated. Outcomes are written only after the setup window closes and never appear as evidence.</p>}</Section>
      </div>
      <Section title="News state and data quality at decision time"><Json value={{ news_state: ev.news_state, data_quality: ev.data_quality, other_candidates: ev.other_candidates }} /></Section>
    </div>
  );
}

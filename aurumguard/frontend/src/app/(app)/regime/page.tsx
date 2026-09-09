"use client";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { fmtTime } from "@/lib/format";

interface R { regime: { primary: string; tags: string[]; confidence: number; trend_direction: string; supporting: string[]; conflicting: string[]; measurements: Record<string, unknown>; version: string } | null; last_change: { ts: string; from: string; to: string } | null; history: { ts: string; regime: string }[]; strategies_allowed: string[]; strategies_prohibited: string[]; as_of: string | null }

export default function Regime() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<R>("/api/regime", 60000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const r = data.regime;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Market regime</h1>
      {r ? (<>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div className="kpi card"><span className="label">Primary</span><span className="value">{r.primary}</span></div>
          <div className="kpi card"><span className="label">Confidence</span><span className="value">{Math.round(r.confidence * 100)}%</span></div>
          <div className="kpi card"><span className="label">Trend direction</span><span className="value">{r.trend_direction}</span></div>
          <div className="kpi card"><span className="label">Tags</span><span className="value text-base">{r.tags.join(", ") || "none"}</span></div>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          <Section title="Supporting measurements"><ul className="text-sm list-disc ps-5">{r.supporting.map((x, i) => <li key={i}>{x}</li>)}</ul></Section>
          <Section title="Conflicting measurements">{r.conflicting.length ? <ul className="text-sm list-disc ps-5">{r.conflicting.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="muted text-sm">none</p>}</Section>
          <Section title="Strategies allowed / prohibited"><p className="text-sm">Allowed: {data.strategies_allowed.join(", ") || "none"}</p><p className="text-sm">Prohibited: {data.strategies_prohibited.join(", ") || "none"}</p></Section>
          <Section title="Last regime change">{data.last_change ? <p className="text-sm">{data.last_change.from} → {data.last_change.to} at {fmtTime(data.last_change.ts, tz)}</p> : <p className="muted text-sm">no change recorded in the retained history</p>}<p className="muted text-xs">Classified at {fmtTime(data.as_of, tz)} · {r.version}</p></Section>
        </div>
        <Section title="Measurements"><Json value={r.measurements} /></Section>
      </>) : <p className="muted">No regime classified yet (the analysis loop has not run for your account, or data is unavailable).</p>}
    </div>
  );
}

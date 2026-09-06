"use client";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, EvidenceList, Loading, Section } from "@/components/ui";
import type { EvidenceItem } from "@/lib/types";

interface Snap { demo_data: boolean; intermarket_evidence: EvidenceItem[]; macro_evidence: EvidenceItem[]; positioning_evidence: EvidenceItem[]; intermarket_series: Record<string, number[]> | null; data_sources: Record<string, string>; data_unavailable: string[] }

function Spark({ values, label }: { values: number[]; label: string }) {
  if (!values?.length) return <p className="muted text-sm">{label}: unavailable</p>;
  const min = Math.min(...values), max = Math.max(...values), w = 240, h = 48;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * h}`).join(" ");
  return <div className="text-sm"><div className="flex justify-between"><span>{label}</span><span className="muted">{values[values.length - 1]} (5d {((values[values.length - 1] - values[Math.max(0, values.length - 6)])).toFixed(3)})</span></div><svg width={w} height={h} role="img" aria-label={`${label} last ${values.length} days`}><polyline fill="none" stroke="var(--accent)" strokeWidth="1.5" points={pts} /></svg></div>;
}

export default function Intermarket() {
  const { settings } = useApp();
  const { data, error } = useApi<Snap>("/api/market/snapshot", 120000);
  void settings;
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading label="Building snapshot" />;
  const s = data.intermarket_series ?? {};
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Intermarket and macro</h1>
      {data.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA — synthetic series</p>}
      <Section title="Daily series (last 60 sessions)"><div className="grid sm:grid-cols-2 gap-3">{[["gold", "Gold (D1 close)"], ["dxy", "Dollar index proxy"], ["us10y", "US 10y yield %"], ["us2y", "US 2y yield %"], ["real_yield", "Real-yield proxy %"], ["risk_index", "Equity index"], ["vol_index", "Volatility index"]].map(([k, l]) => <Spark key={k} values={s[k] ?? []} label={l} />)}</div></Section>
      <div className="grid md:grid-cols-3 gap-3">
        <Section title="Intermarket evidence"><EvidenceList items={data.intermarket_evidence} /></Section>
        <Section title="Macro evidence"><EvidenceList items={data.macro_evidence} /></Section>
        <Section title="Positioning and public flows (slow-moving)"><EvidenceList items={data.positioning_evidence} /><p className="muted text-xs mt-2">Weekly positioning and ETF flows are lagged public data. They are never presented as real-time institutional flow.</p></Section>
      </div>
      <Section title="Sources"><ul className="text-sm">{Object.entries(data.data_sources).map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul>{data.data_unavailable.length ? <p className="text-sm" style={{ color: "var(--sell)" }}>Unavailable: {data.data_unavailable.join("; ")}</p> : null}</Section>
    </div>
  );
}

"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Loading, Section } from "@/components/ui";
import type { Candle } from "@/lib/types";

const CandleChart = dynamic(() => import("@/components/CandleChart").then((m) => m.CandleChart), { ssr: false, loading: () => <Loading label="Chart" /> });
const TFS = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"];
interface Structure { trend: string; atr: number | null; volatility: string; levels: { name: string; price: number; kind: string }[]; events: { kind: string; direction: string; label: string; detail: string; ts: string }[]; range: { is_range: boolean; high: number; low: number; width_atr: number } | null }

export default function Charts() {
  const { theme } = useApp();
  const [tf, setTf] = useState("H1");
  const { data, error } = useApi<{ candles: Candle[]; demo_data: boolean }>(`/api/market/candles?timeframe=${tf}&bars=400`, 60000, [tf]);
  const { data: st } = useApi<Structure>(`/api/market/structure?timeframe=${tf}`, 60000, [tf]);
  const dark = theme === "dark" || (theme === "system" && typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const levels = (st?.levels ?? []).filter((l) => ["PDH", "PDL", "PWH", "PWL"].includes(l.name)).map((l) => ({ price: l.price, label: l.name, color: l.kind === "resistance" ? "#b3261e" : "#1b7f4b" }));
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Multi-timeframe charts</h1>
      <div role="tablist" aria-label="Timeframe" className="flex gap-2 mb-3 flex-wrap">{TFS.map((x) => <button key={x} role="tab" aria-selected={tf === x} className={`btn ${tf === x ? "btn-primary" : ""}`} onClick={() => setTf(x)}>{x}</button>)}</div>
      <ErrorBox error={error} />
      <div className="card mb-4">{data ? <CandleChart candles={data.candles} levels={levels} dark={dark} /> : <Loading />}<p className="muted text-xs mt-1">{data?.demo_data ? "DEMO DATA (synthetic). " : ""}Closed bars only are used by the engine; the forming bar is shown for context. Dashed lines: previous day/week high/low. Purple: EMA20.</p></div>
      <Section title={`Structure snapshot (${tf})`}>
        {st ? <div className="text-sm space-y-1"><p>Trend: <strong>{st.trend}</strong> · ATR(14): {st.atr?.toFixed(2)} · Volatility: {st.volatility} {st.range ? `· Range: ${st.range.is_range ? "yes" : "no"} (${st.range.low.toFixed(2)}–${st.range.high.toFixed(2)}, ${st.range.width_atr} ATR)` : ""}</p>
          <p className="muted">Levels: {st.levels.map((l) => `${l.name} ${l.price.toFixed(2)}`).join(" · ")}</p>
          <ul>{st.events.map((e, i) => <li key={i}><strong>{e.kind}</strong> ({e.direction}) — {e.label}: {e.detail}</li>)}</ul></div> : <Loading />}
      </Section>
    </div>
  );
}

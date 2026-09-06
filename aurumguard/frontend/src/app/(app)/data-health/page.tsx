"use client";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { fmtTime } from "@/lib/format";

interface H { demo_data: boolean; providers: { name: string; kind: string; ok: boolean; is_mock: boolean; last_success: string | null; last_error: string | null; latency_ms: number | null; consecutive_failures: number; notes: string[]; doc: Record<string, unknown> | null }[]; analysis_runs: { ts: string; as_of: string; users: number; duration_ms: number; data_status: string }[] }

export default function DataHealth() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<H>("/api/market/health", 30000);
  const { data: snap } = useApi<{ quote_integrity: Record<string, unknown>; candle_integrity: Record<string, unknown> }>("/api/market/snapshot", 60000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Data-provider health</h1>
      {data.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA — mock providers active</p>}
      <Section title="Providers"><div className="scroll-x"><table className="table"><thead><tr><th>Kind</th><th>Name</th><th>OK</th><th>Mock</th><th>Last success</th><th>Failures</th><th>Latency</th><th>Notes</th></tr></thead><tbody>{data.providers.map((p) => <tr key={p.kind + p.name}><td>{p.kind}</td><td>{p.name}</td><td>{p.ok ? "✓" : "✗"}</td><td>{p.is_mock ? "yes" : "no"}</td><td>{fmtTime(p.last_success, tz)}</td><td>{p.consecutive_failures}{p.last_error ? ` (${p.last_error})` : ""}</td><td>{p.latency_ms ?? "–"}</td><td className="text-xs">{p.notes.join("; ")}</td></tr>)}</tbody></table></div></Section>
      <Section title="Integrity checks (current)">{snap ? <Json value={{ quote: snap.quote_integrity, candles: snap.candle_integrity }} /> : <Loading />}</Section>
      <Section title="Analysis runs"><div className="scroll-x"><table className="table"><thead><tr><th>Run</th><th>As of</th><th>Users</th><th>Duration</th><th>Data</th></tr></thead><tbody>{data.analysis_runs.map((r, i) => <tr key={i}><td>{fmtTime(r.ts, tz)}</td><td>{fmtTime(r.as_of, tz)}</td><td>{r.users}</td><td>{r.duration_ms} ms</td><td>{r.data_status}</td></tr>)}</tbody></table></div></Section>
      <Section title="Provider documentation">{data.providers.filter((p) => p.doc).map((p) => <details key={p.kind}><summary className="text-sm">{p.kind}: {p.name}</summary><Json value={p.doc} /></details>)}</Section>
    </div>
  );
}

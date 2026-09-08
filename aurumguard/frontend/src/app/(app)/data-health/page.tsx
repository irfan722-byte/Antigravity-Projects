"use client";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { fmtTime } from "@/lib/format";
import { fmtAge } from "@/components/DataView";

interface Integrity { subject?: string; status: string; freshness_seconds: number | null; checked_at: string; issues: { code: string; severity: string; message: string }[] }
interface H { demo_data: boolean; providers: { name: string; kind: string; ok: boolean; is_mock: boolean; last_success: string | null; last_error: string | null; latency_ms: number | null; consecutive_failures: number; notes: string[]; doc: Record<string, unknown> | null }[]; analysis_runs: { ts: string; as_of: string; users: number; duration_ms: number; data_status: string }[] }

export default function DataHealth() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<H>("/api/market/health", 30000);
  const { data: snap } = useApi<{ quote_integrity: Integrity | null; candle_integrity: Record<string, Integrity> }>("/api/market/snapshot", 60000);
  const checks: (Integrity & { name: string })[] = snap ? [...(snap.quote_integrity ? [{ name: "Quote", ...snap.quote_integrity }] : []), ...Object.entries(snap.candle_integrity ?? {}).map(([tf, r]) => ({ name: `Candles ${tf}`, ...r }))] : [];
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Data-provider health</h1>
      {data.demo_data && <p className="demo-banner rounded mb-3">DEMO DATA — mock providers active</p>}
      <Section title="Providers"><div className="scroll-x"><table className="table"><thead><tr><th>Kind</th><th>Name</th><th>OK</th><th>Mock</th><th>Last success</th><th>Failures</th><th>Latency</th><th>Notes</th></tr></thead><tbody>{data.providers.map((p) => <tr key={p.kind + p.name}><td>{p.kind}</td><td>{p.name}</td><td>{p.ok ? "✓" : "✗"}</td><td>{p.is_mock ? "yes" : "no"}</td><td>{fmtTime(p.last_success, tz)}</td><td>{p.consecutive_failures}{p.last_error ? ` (${p.last_error})` : ""}</td><td>{p.latency_ms ?? "–"}</td><td className="text-xs">{p.notes.join("; ")}</td></tr>)}</tbody></table></div></Section>
      <Section title="Integrity checks (current)">{!snap ? <Loading /> : !checks.length ? <p className="muted text-sm">No snapshot yet.</p> : <div className="scroll-x"><table className="table"><thead><tr><th>Check</th><th>Status</th><th>Age of latest data</th><th>Checked</th><th>Issues</th></tr></thead><tbody>{checks.map((c) => <tr key={c.name}><td>{c.name}</td><td><span className={`badge integrity-${c.status}`}>{c.status}</span></td><td>{fmtAge(c.freshness_seconds)}</td><td>{fmtTime(c.checked_at, tz)}</td><td className="text-xs">{c.issues?.length ? c.issues.map((i) => `${i.severity} ${i.code}: ${i.message}`).join("; ") : "none"}</td></tr>)}</tbody></table></div>}</Section>
      <Section title="Analysis runs"><div className="scroll-x"><table className="table"><thead><tr><th>Run</th><th>As of</th><th>Users</th><th>Duration</th><th>Data</th></tr></thead><tbody>{data.analysis_runs.map((r, i) => <tr key={i}><td>{fmtTime(r.ts, tz)}</td><td>{fmtTime(r.as_of, tz)}</td><td>{r.users}</td><td>{r.duration_ms} ms</td><td>{r.data_status}</td></tr>)}</tbody></table></div></Section>
      <Section title="Provider documentation">{data.providers.filter((p) => p.doc).map((p) => <details key={p.kind}><summary className="text-sm">{p.kind}: {p.name}</summary><Json value={p.doc} /></details>)}</Section>
    </div>
  );
}

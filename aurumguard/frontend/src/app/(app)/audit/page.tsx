"use client";
import { useApp, useApi } from "@/components/Providers";
import { ErrorBox, Loading, Section } from "@/components/ui";
import { fmtTime } from "@/lib/format";

interface A { items: { id: number; ts: string; actor: string; action: string; subject: string; detail: Record<string, unknown>; row_hash: string }[]; chain: { rows: number; ok: boolean; broken_ids: number[] } | null }

export default function Audit() {
  const { settings } = useApp(); const tz = settings?.timezone ?? "UTC";
  const { data, error } = useApi<A>("/api/audit?limit=200", 30000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Audit dashboard</h1>
      {data.chain && <p className="card mb-3 text-sm">Hash chain over last {data.chain.rows} rows: <strong style={{ color: data.chain.ok ? "var(--buy)" : "var(--sell)" }}>{data.chain.ok ? "intact" : `BROKEN at ${data.chain.broken_ids.join(", ")}`}</strong></p>}
      <Section title="Entries"><div className="scroll-x"><table className="table"><thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Subject</th><th>Detail</th><th>Hash</th></tr></thead><tbody>{data.items.map((r) => <tr key={r.id}><td>{r.id}</td><td>{fmtTime(r.ts, tz)}</td><td>{r.actor.slice(0, 10)}</td><td>{r.action}</td><td>{r.subject.slice(0, 24)}</td><td className="text-xs">{JSON.stringify(r.detail).slice(0, 160)}</td><td className="text-xs">{r.row_hash.slice(0, 10)}</td></tr>)}</tbody></table></div></Section>
    </div>
  );
}

"use client";
import { useState } from "react";
import { summarize } from "@/components/DataView";
import { useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";
import { api } from "@/lib/api";

export default function Admin() {
  const { data, error, refresh } = useApi<Record<string, unknown>>("/api/admin/overview", 30000);
  const [msg, setMsg] = useState<string | null>(null);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Administration</h1>
      <Section title="Environment"><Json value={{ environment: data.environment, providers: data.providers, demo_data: data.demo_data, scheduler_running: data.scheduler_running, live_execution: data.live_execution, users: data.users }} />{(data.config_problems as string[]).length ? <ul className="text-sm" style={{ color: "var(--sell)" }}>{(data.config_problems as string[]).map((p, i) => <li key={i}>{p}</li>)}</ul> : <p className="text-sm">No configuration problems for this environment.</p>}</Section>
      <Section title="Strategies"><Json value={data.strategies} /></Section>
      <Section title="Analysis runs"><Json value={data.analysis_runs} /><button className="btn mt-2" onClick={async () => { try { const r = await api<Record<string, unknown>>("/api/admin/run-analysis", { method: "POST" }); setMsg(summarize(r, undefined, 300)); refresh(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } }}>Run analysis now</button>{msg && <p role="status" className="text-xs mt-1">{msg}</p>}</Section>
    </div>
  );
}

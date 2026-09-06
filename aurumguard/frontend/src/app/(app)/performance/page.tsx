"use client";
import { useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";

interface Perf { strategies: { id: string; name: string; status: string; horizon: string; validation: Record<string, unknown>; in_sample: Record<string, unknown>; out_of_sample: Record<string, unknown>; paper: Record<string, unknown>; rolling_paper: Record<string, unknown> }[]; note: string; demo_data: boolean }
interface PaperPerf { portfolio?: Record<string, unknown>; by_horizon?: Record<string, Record<string, unknown>>; trades?: number }

const KEYS = ["trades", "win_rate", "expectancy_r", "profit_factor", "max_drawdown_r"];

export default function Performance() {
  const { data, error } = useApi<Perf>("/api/performance/strategies", 60000);
  const { data: pp } = useApi<PaperPerf>("/api/paper/performance", 60000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const cell = (o: Record<string, unknown> | undefined, k: string) => { const v = o?.[k]; return v === undefined || v === null ? "–" : typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(3)) : String(v); };
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Performance dashboard</h1>
      <p className="muted text-sm mb-3">{data.note}{data.demo_data ? " All figures below come from DEMO (synthetic) data." : ""}</p>
      <Section title="By strategy: in-sample vs out-of-sample vs paper"><div className="scroll-x"><table className="table"><thead><tr><th>Strategy</th><th>Status</th>{["IS", "OOS", "Paper"].flatMap((s) => KEYS.map((k) => <th key={s + k}>{s} {k.replace(/_/g, " ")}</th>))}</tr></thead><tbody>
        {data.strategies.map((s) => <tr key={s.id}><td>{s.id}</td><td>{s.status}</td>{KEYS.map((k) => <td key={"is" + k}>{cell(s.in_sample, k)}</td>)}{KEYS.map((k) => <td key={"oos" + k}>{cell(s.out_of_sample, k)}</td>)}{KEYS.map((k) => <td key={"p" + k}>{cell(s.paper, k)}</td>)}</tr>)}
      </tbody></table></div></Section>
      {data.strategies.map((s) => <Section key={s.id} title={`${s.id} out-of-sample detail`}><Json value={{ expectancy_ci95: s.out_of_sample.expectancy_r_ci95_bootstrap, brier: s.out_of_sample.brier, calibration_buckets: s.out_of_sample.calibration_buckets, validated_at: s.validation.validated_at, data_label: s.validation.data_label, rolling_paper: s.rolling_paper }} /></Section>)}
      <Section title="Paper portfolio (this account)">{pp?.portfolio ? <Json value={{ ...pp.portfolio, equity_curve: undefined, by_month: undefined }} /> : <p className="muted text-sm">No closed paper trades yet.</p>}{pp?.by_horizon ? <details><summary className="text-sm">By horizon</summary><Json value={pp.by_horizon} /></details> : null}</Section>
    </div>
  );
}

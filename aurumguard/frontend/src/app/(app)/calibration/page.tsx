"use client";
import { useApi } from "@/components/Providers";
import { ErrorBox, Json, Loading, Section } from "@/components/ui";

interface Cal { version: string; live_outcomes: { bucket: string; n: number; observed_win_rate: number; predicted_mid: number }[]; brier_live: number | null; sample: number; strategies: Record<string, { validation_buckets: Record<string, { n: number; wins: number }> | null; brier_validation: number | null }>; note: string }

export default function Calibration() {
  const { data, error } = useApi<Cal>("/api/calibration", 60000);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const w = 320, h = 200;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Probability calibration</h1>
      <p className="muted text-sm mb-3">{data.note} Method: {data.version}.</p>
      <div className="grid md:grid-cols-2 gap-3">
        <Section title={`Reliability diagram (live outcomes, n=${data.sample})`}>
          <svg width={w} height={h} role="img" aria-label="Reliability diagram: predicted versus observed win rate">
            <line x1={20} y1={h - 20} x2={w - 10} y2={10} stroke="var(--muted)" strokeDasharray="4 4" />
            <line x1={20} y1={h - 20} x2={w - 10} y2={h - 20} stroke="var(--border)" /><line x1={20} y1={10} x2={20} y2={h - 20} stroke="var(--border)" />
            {data.live_outcomes.map((b) => <circle key={b.bucket} cx={20 + b.predicted_mid * (w - 30)} cy={h - 20 - b.observed_win_rate * (h - 30)} r={4 + Math.min(10, b.n / 5)} fill="var(--accent)" opacity={0.8}><title>{`${b.bucket}: predicted ${b.predicted_mid}, observed ${b.observed_win_rate}, n=${b.n}`}</title></circle>)}
            <text x={w / 2} y={h - 4} fontSize={10} fill="currentColor" textAnchor="middle">predicted</text><text x={8} y={h / 2} fontSize={10} fill="currentColor" transform={`rotate(-90 8 ${h / 2})`} textAnchor="middle">observed</text>
          </svg>
          <p className="text-sm">Brier (live): {data.brier_live ?? "n/a"}</p>
          {data.live_outcomes.length ? <table className="table"><thead><tr><th>Score bucket</th><th>n</th><th>Predicted mid</th><th>Observed</th></tr></thead><tbody>{data.live_outcomes.map((b) => <tr key={b.bucket}><td>{b.bucket}</td><td>{b.n}</td><td>{b.predicted_mid}</td><td>{b.observed_win_rate}</td></tr>)}</tbody></table> : <p className="muted text-sm">No evaluated outcomes yet.</p>}
        </Section>
        <Section title="Validation buckets per strategy"><Json value={data.strategies} /></Section>
      </div>
    </div>
  );
}

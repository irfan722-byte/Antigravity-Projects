import Link from "next/link";

export default function Welcome() {
  return (
    <main id="main" className="max-w-3xl mx-auto p-6 space-y-5">
      <h1 className="text-3xl font-extrabold" style={{ color: "var(--accent)" }}>AurumGuard</h1>
      <p className="text-lg">Rule-based XAU/USD analysis, risk management, paper trading and mobile notifications.</p>
      <section className="card space-y-2" aria-labelledby="disclosure">
        <h2 id="disclosure" className="font-bold">Please read before you continue</h2>
        <ul className="list-disc ps-5 text-sm space-y-1">
          <li>AurumGuard produces rule-based analysis from public and licensed data. It is not investment advice and it is not a recommendation to buy or sell anything.</li>
          <li>No outcome is guaranteed. Every setup is uncertain and can lose money, including the full amount risked. Past performance, backtests and paper results do not predict future results.</li>
          <li>The application has no regulatory approval in any jurisdiction. A jurisdiction-specific legal and compliance review is required before any commercial or live use.</li>
          <li>Automatic live order execution is disabled. The MVP supports analysis and paper trading only.</li>
          <li>Demo mode uses synthetic data, clearly labelled DEMO DATA. It does not reflect the real market.</li>
          <li>We store only what the service needs: your email, password hash, settings, decisions, paper trades and notifications. You can export or delete your account at any time.</li>
        </ul>
      </section>
      <div className="flex gap-3"><Link href="/register" className="btn btn-primary">Create account and accept</Link><Link href="/login" className="btn">Log in</Link></div>
      <p className="muted text-xs">Legal review placeholder: [jurisdiction-specific terms, privacy notice and risk warnings to be inserted after counsel review].</p>
    </main>
  );
}

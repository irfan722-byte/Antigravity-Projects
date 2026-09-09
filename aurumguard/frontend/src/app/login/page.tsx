"use client";
import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { useApp } from "@/components/Providers";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { reload } = useApp();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [mfa, setMfa] = useState(""); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await api<{ access_token: string; refresh_token: string; onboarding_completed: boolean }>("/api/auth/login", { method: "POST", auth: false, body: { email, password, mfa_code: mfa || null } });
      setTokens(r.access_token, r.refresh_token); await reload();
      router.replace(r.onboarding_completed ? (params.get("next") ?? "/dashboard") : "/onboarding");
    } catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)); } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="card space-y-3" aria-label="Log in">
      <label className="block text-sm">Email<input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
      <label className="block text-sm">Password<input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <label className="block text-sm">MFA code (if enabled)<input className="input" inputMode="numeric" value={mfa} onChange={(e) => setMfa(e.target.value)} /></label>
      {err && <p role="alert" style={{ color: "var(--sell)" }}>{err}</p>}
      <button className="btn btn-primary" disabled={busy}>Log in</button>
      <p className="text-sm muted">No account? <Link href="/register">Register</Link>. Demo credentials are printed by the seed script.</p>
    </form>
  );
}
export default function Login() { return <main id="main" className="max-w-md mx-auto p-6"><h1 className="text-2xl font-bold mb-4">Log in</h1><Suspense><LoginForm /></Suspense></main>; }

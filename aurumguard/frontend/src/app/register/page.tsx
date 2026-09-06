"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { useApp } from "@/components/Providers";

export default function Register() {
  const router = useRouter(); const { reload } = useApp();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [accept, setAccept] = useState(false); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const r = await api<{ access_token: string; refresh_token: string }>("/api/auth/register", { method: "POST", auth: false, body: { email, password, accept_disclosure: accept } });
      setTokens(r.access_token, r.refresh_token); await reload(); router.replace("/onboarding");
    } catch (ex) { setErr(ex instanceof Error ? ex.message : String(ex)); } finally { setBusy(false); }
  }
  return (
    <main id="main" className="max-w-md mx-auto p-6"><h1 className="text-2xl font-bold mb-4">Create account</h1>
      <form onSubmit={submit} className="card space-y-3">
        <label className="block text-sm">Email<input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="block text-sm">Password (12+ chars, mixed case, a digit)<input className="input" type="password" autoComplete="new-password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <label className="flex gap-2 text-sm items-start"><input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} required /><span>I have read the disclosure: this is analysis and paper trading for education and personal research, not advice; losses are possible; no regulatory approval is claimed.</span></label>
        {err && <p role="alert" style={{ color: "var(--sell)" }}>{err}</p>}
        <button className="btn btn-primary" disabled={busy || !accept}>Create account</button>
      </form>
    </main>
  );
}

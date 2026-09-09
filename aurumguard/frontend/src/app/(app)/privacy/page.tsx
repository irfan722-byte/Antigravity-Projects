"use client";
import { useState } from "react";
import { Section } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/components/Providers";

export default function Privacy() {
  const { logout } = useApp();
  const [pw, setPw] = useState(""); const [confirm, setConfirm] = useState(""); const [msg, setMsg] = useState<string | null>(null);
  async function exportData() { const d = await api<unknown>("/api/users/export"); const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "aurumguard-export.json"; a.click(); }
  async function del() { try { await api("/api/users/delete", { method: "POST", body: { password: pw, confirm } }); logout(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); } }
  return (
    <div>
      <h1 className="text-2xl font-bold mb-3">Privacy controls</h1>
      <Section title="What we store"><ul className="text-sm list-disc ps-5"><li>Email and password hash (Argon2), optional MFA secret.</li><li>Settings: timezone, currency, risk limits, notification preferences.</li><li>Decisions, evidence, paper orders/positions and notifications generated for your account.</li><li>Push subscription endpoints (hashed for lookup), if you enable push.</li><li>Audit-log entries for actions you take.</li></ul><p className="muted text-xs">No broker credentials, banking details or PINs are ever requested or stored.</p></Section>
      <Section title="Export"><button className="btn" onClick={exportData}>Download my data (JSON)</button></Section>
      <Section title="Delete account"><p className="text-sm mb-2">Removes personal data immediately. Decision and paper records are retained pseudonymously for audit integrity. Type <code>DELETE MY ACCOUNT</code> to confirm.</p><input className="input mb-2" type="password" placeholder="Password" value={pw} onChange={(e) => setPw(e.target.value)} /><input className="input mb-2" placeholder="DELETE MY ACCOUNT" value={confirm} onChange={(e) => setConfirm(e.target.value)} /><button className="btn" style={{ borderColor: "var(--sell)", color: "var(--sell)" }} onClick={del} disabled={confirm !== "DELETE MY ACCOUNT"}>Delete my account</button>{msg && <p role="alert" className="text-sm mt-2">{msg}</p>}</Section>
    </div>
  );
}

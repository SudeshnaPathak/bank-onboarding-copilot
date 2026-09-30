import { Landmark } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const DEMO = [
  { label: "Customer (Priya)", email: "priya@example.com" },
  { label: "Bank analyst (Ravi)", email: "ravi@bank.example.com" },
];

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const u = await login(email.trim(), password);
      nav(u.role === "analyst" ? "/review" : "/apply", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
    } finally { setBusy(false); }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="brand big"><Landmark size={26} /> Onboarding Copilot</div>
        <p className="muted">Open a bank account in minutes. A human reviewer always makes the final decision.</p>
        <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="username" required /></label>
        <label>Password<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" required /></label>
        {error && <div className="alert" role="alert">{error}</div>}
        <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <div className="demo-login">
          <span className="muted small">Demo accounts (password demo1234)</span>
          <div className="row">
            {DEMO.map((d) => (
              <button type="button" key={d.email} className="btn btn-ghost" onClick={() => { setEmail(d.email); setPassword("demo1234"); }}>{d.label}</button>
            ))}
          </div>
        </div>
      </form>
    </main>
  );
}

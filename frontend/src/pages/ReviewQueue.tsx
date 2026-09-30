import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { QueueRow } from "../api/types";
import { Layout } from "../components/Layout";
import { SeverityBadge } from "../components/Review";

export default function ReviewQueue() {
  const [rows, setRows] = useState<QueueRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<{ valid: boolean; entries: number } | null>(null);

  useEffect(() => {
    const load = () => api.queue().then(setRows).catch((e) => setError(String(e.message ?? e)));
    load();
    api.verifyAudit().then(setAudit).catch(() => undefined);
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <Layout subtitle="Review queue">
      <main className="page">
        <div className="page-head">
          <h1>Applications awaiting review</h1>
          {audit && <span className={`chip ${audit.valid ? "chip-ok" : "chip-warn"}`}>Audit chain {audit.valid ? "verified" : "BROKEN"} · {audit.entries} entries</span>}
        </div>
        {error && <div className="alert">{error}</div>}
        {rows && rows.length === 0 && <div className="empty">Nothing waiting. Submit an application as the customer to see it here.</div>}
        {rows && rows.length > 0 && (
          <table className="table">
            <thead><tr><th>Customer</th><th>Score</th><th>Flags</th><th>Top severity</th><th>Submitted</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.customer}{r.submission_no > 1 && <span className="chip"> resubmission</span>}</td>
                  <td>{r.analysis_ready ? <span className={`score score-${r.band}`}>{r.score}</span> : <span className="muted">analysing…</span>}</td>
                  <td>{r.flag_count}</td>
                  <td>{r.top_severity ? <SeverityBadge s={r.top_severity} /> : <span className="muted">none</span>}</td>
                  <td>{new Date(r.submitted_at).toLocaleString()}</td>
                  <td><Link className="btn btn-primary" to={`/review/${r.id}`}>Review</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </Layout>
  );
}

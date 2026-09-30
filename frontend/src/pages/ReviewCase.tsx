import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ReviewDetail } from "../api/types";
import { Layout } from "../components/Layout";
import { FlagList, ScoreDial } from "../components/Review";

function PageImage({ caseId, docId, page, label }: { caseId: string; docId: string; page: number; label: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    api.documentImage(caseId, docId, page).then((u) => { url = u; setSrc(u); }).catch(() => setSrc(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [caseId, docId, page]);
  return src ? <img className="doc-img" src={src} alt={label} /> : <div className="doc-img placeholder muted">Loading…</div>;
}

// PDFs are rendered to page images on the server, so multi-page documents show as a stack of images.
function DocImage({ caseId, doc }: { caseId: string; doc: ReviewDetail["documents"][number] }) {
  const pages = Math.max(1, doc.pages);
  return (
    <div className="doc-pages">
      {doc.quality.pdf_kind && (
        <div className="muted small">PDF ({doc.quality.pdf_kind === "text" ? "text layer, read directly" : "scanned, read with OCR"})</div>
      )}
      {Array.from({ length: pages }, (_, i) => (
        <div key={i}>
          <PageImage caseId={caseId} docId={doc.id} page={i} label={pages > 1 ? `${doc.label}, page ${i + 1}` : doc.label} />
          {pages > 1 && <div className="muted small">Page {i + 1} of {pages}</div>}
        </div>
      ))}
    </div>
  );
}

export default function ReviewCase() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<"approve" | "request_info" | "reject">("approve");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.reviewDetail(id).then(setD).catch((e) => setError(e.message)); }, [id]);

  async function decide() {
    setBusy(true); setError(null);
    try {
      await api.decide(id, action, note);
      nav("/review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not record the decision");
    } finally { setBusy(false); }
  }

  if (error && !d) return <Layout subtitle="Case"><main className="page"><div className="alert">{error}</div></main></Layout>;
  if (!d) return <Layout subtitle="Case"><main className="page muted">Loading…</main></Layout>;
  const a = d.analysis;
  const needsNote = action !== "approve";

  return (
    <Layout subtitle={`Case for ${d.customer.name}`}>
      <main className="page">
        <Link to="/review" className="back"><ArrowLeft size={14} /> Queue</Link>
        <div className="page-head"><h1>{d.customer.name} <span className="muted small">{d.customer.email}</span></h1><span className="chip">{d.status.replace("_", " ")}</span></div>

        <div className="grid">
          <section className="panel wide">
            <h2>Rule findings</h2>
            {a ? <><ScoreDial score={a.score} band={a.band} /><FlagList flags={a.flags} /></> : <div className="alert">Automated analysis is unavailable for this case. You can still review the documents and decide.</div>}
          </section>

          <section className="panel">
            <h2>Summary</h2>
            {a ? <><p style={{ whiteSpace: "pre-wrap" }}>{a.summary}</p>
              <p className="muted small">Text describing the rule results above. It does not make or suggest a decision.</p></> : <p className="muted">None.</p>}
          </section>

          <section className="panel">
            <h2>Applicant details</h2>
            <dl className="kv">{d.details.map((x) => <div className="kv-row" key={x.label}><dt>{x.label}</dt><dd>{x.value}{x.confirmed_by_customer && <span className="chip chip-ok"> confirmed</span>}</dd></div>)}</dl>
          </section>

          <section className="panel wide">
            <h2>Documents</h2>
            <div className="docs-grid">
              {d.documents.map((doc) => (
                <figure key={doc.id}>
                  <DocImage caseId={d.id} doc={doc} />
                  <figcaption><strong>{doc.label}</strong>
                    <dl className="kv small">{doc.fields.map((f) => <div className="kv-row" key={f.key}><dt>{f.label}</dt><dd>{f.value}{f.confidence != null && f.confidence < 0.8 && <span className="chip chip-warn"> {Math.round(f.confidence * 100)}%</span>}</dd></div>)}</dl>
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>

          {a && (
            <section className="panel">
              <h2>How the score was calculated</h2>
              <table className="table compact"><tbody>
                {a.breakdown.length === 0 && <tr><td className="muted">No penalties.</td></tr>}
                {a.breakdown.map((b, i) => <tr key={i}><td>{b.title}</td><td>−{b.penalty}{b.reduced_because_confirmed && <span className="muted small"> (halved: confirmed)</span>}</td></tr>)}
              </tbody></table>
              <p className="muted small">Rules v{a.provenance.rules?.version} · {a.provenance.rules?.sha256} · summary by {a.provenance.summariser}</p>
            </section>
          )}

          <section className="panel">
            <h2>Audit trail</h2>
            <ul className="timeline">{d.audit.map((e) => <li key={e.id}><span className="muted small">{new Date(e.ts).toLocaleTimeString()}</span> <code>{e.action}</code> <span className="muted small">{e.actor}</span></li>)}</ul>
          </section>

          {d.can_decide && (
            <section className="panel wide decision">
              <h2>Your decision</h2>
              <p className="muted small">You make this decision. The system never approves or rejects on its own.</p>
              <div className="seg" role="radiogroup">
                {([["approve", "Approve"], ["request_info", "Request information"], ["reject", "Reject"]] as const).map(([v, l]) => (
                  <button key={v} role="radio" aria-checked={action === v} className={`seg-btn ${action === v ? "on" : ""} seg-${v}`} onClick={() => setAction(v)}>{l}</button>
                ))}
              </div>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder={needsNote ? "Note for the customer and the record (required)" : "Optional note"} />
              {error && <div className="alert" role="alert">{error}</div>}
              <button className="btn btn-primary" disabled={busy || (needsNote && note.trim().length < 5)} onClick={decide}>Confirm {action.replace("_", " ")}</button>
            </section>
          )}
          {d.decisions.length > 0 && <section className="panel wide"><h2>Decisions</h2>{d.decisions.map((x, i) => <div key={i}><strong>{x.action.replace("_", " ")}</strong> <span className="muted small">{new Date(x.at).toLocaleString()}</span> {x.note}</div>)}</section>}
        </div>
      </main>
    </Layout>
  );
}

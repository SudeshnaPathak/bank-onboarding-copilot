import { RotateCcw, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { CaseView, ChatMessage, DemoScenario, StreamEvent, TraceItem } from "../api/types";
import type { CardHandlers } from "../components/Cards";
import { ChatThread } from "../components/ChatThread";
import { Layout } from "../components/Layout";
import { AgentActivity, ProgressRail } from "../components/Sidebar";

const DOC_ORDER = ["pan", "aadhaar", "driving_licence"];
const EDITABLE = new Set(["draft", "info_requested"]);

const PLACEHOLDER: Record<string, string> = {
  upload: "Ask a question, or upload your document above…",
  confirm: "Or type the correct value here…",
  field: "Type your answer…",
  ready: "Ask a question, or press Submit for review…",
};

export default function Apply() {
  const [view, setView] = useState<CaseView | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<TraceItem[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [samples, setSamples] = useState<DemoScenario[] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const run = useCallback(async (start: () => Promise<AsyncGenerator<StreamEvent>>, optimistic?: string): Promise<CaseView | null> => {
    setBusy(true); setError(null); setLive([]); setPending(optimistic ?? null);
    let latest: CaseView | null = null;
    try {
      for await (const ev of await start()) {
        if (ev.event === "node") setLive((l) => [...l, ev.data]);
        else if (ev.event === "state") { latest = ev.data; setView(ev.data); }
        else if (ev.event === "error") setError(ev.data.message);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally { setBusy(false); setPending(null); setLive([]); }
    return latest;
  }, []);

  // open (or resume) the customer's case; greet once (the ref also guards React StrictMode's double effect in dev)
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    (async () => {
      const v = await api.openCase();
      setView(v);
      if (v.messages.length === 0) await run(() => api.chat(v.id, { action: { type: "start" } }));
    })().catch((e) => setError(e instanceof Error ? e.message : "Could not open your application"));
    api.demoSamples().then(setSamples).catch(() => setSamples([]));
  }, [run]);

  // while a reviewer is deciding, poll so the outcome appears without a refresh
  useEffect(() => {
    if (!view || view.status !== "under_review") return;
    const t = setInterval(() => api.getCase(view.id).then(setView).catch(() => undefined), 4000);
    return () => clearInterval(t);
  }, [view]);

  const caseId = view?.id;
  const send = (payload: { text?: string; action?: Record<string, unknown> }, optimistic?: string) =>
    caseId ? run(() => api.chat(caseId, payload), optimistic) : Promise.resolve(null);

  const uploadBlob = (docType: string, blob: Blob, name: string) =>
    caseId ? run(() => api.upload(caseId, docType, blob, name), "Uploading your document…") : Promise.resolve(null);

  async function useSample(scenario: string, docType: string) {
    const blob = await api.demoSampleBlob(scenario, docType);
    return uploadBlob(docType.replace("_retake", ""), blob, `${docType}.png`);
  }

  async function useScenario(s: DemoScenario) {
    setPickerOpen(false);
    let current = view;
    for (const doc of DOC_ORDER) {
      if (!s.documents.includes(doc) || current?.documents.some((d) => d.doc_type === doc)) continue;
      current = await useSample(s.key, doc);
      if (!current?.documents.some((d) => d.doc_type === doc)) break; // rejected (e.g. blurry): stop so the customer sees why
    }
  }

  async function resetDemo() {
    await api.demoReset();
    setView(null);
    const v = await api.openCase();
    setView(v);
    await run(() => api.chat(v.id, { action: { type: "start" } }));
  }

  const handlers: CardHandlers = {
    busy,
    onAction: (action) => { void send({ action }); },
    onFile: (docType, file) => { void uploadBlob(docType, file, file.name); },
    onSamples: samples && samples.length > 0 ? () => setPickerOpen(true) : undefined,
  };

  const messages = useMemo<ChatMessage[]>(() => {
    const base = view?.messages ?? [];
    return pending ? [...base, { id: "pending", role: "user", text: pending, ui: null, created_at: "" }] : base;
  }, [view, pending]);

  const trace = useMemo(() => (view?.messages ?? []).flatMap((m) => m.trace ?? []).slice(-14), [view]);
  const editable = view ? EDITABLE.has(view.status) : false;
  const currentDoc = view?.next_step.doc_type ?? DOC_ORDER.find((d) => !view?.documents.some((x) => x.doc_type === d)) ?? "pan";

  function submitText() {
    const t = text.trim();
    if (!t || busy || !view) return;
    setText("");
    void send({ text: t }, t);
  }

  return (
    <Layout subtitle={view?.product_name ?? "Savings account"}>
      <div className="apply">
        <section className="chat">
          {view?.status && view.status !== "draft" && <div className={`banner banner-${view.status}`}>{statusBanner(view.status)}</div>}
          <ChatThread messages={messages} busy={busy} live={live} h={handlers} />
          {error && <div className="alert" role="alert">{error}</div>}
          <div className="composer">
            <input value={text} disabled={busy || !editable} data-testid="composer"
              placeholder={editable ? PLACEHOLDER[view?.next_step.kind ?? "field"] ?? "Type a message…" : "This application is closed for editing"}
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submitText()} maxLength={2000} />
            <button className="btn btn-primary" onClick={submitText} disabled={busy || !editable || !text.trim()} aria-label="Send"><Send size={16} /></button>
          </div>
        </section>

        <aside className="side">
          {view && <section className="panel"><h3>Your progress</h3><ProgressRail steps={view.progress} /></section>}
          {view && view.documents.length > 0 && (
            <section className="panel"><h3>Documents</h3>
              <ul className="docs">{view.documents.map((d) => <li key={d.id}>{d.label}</li>)}</ul>
            </section>
          )}
          <AgentActivity trace={trace} />
          <section className="panel"><h3>Demo tools</h3>
            <button className="btn btn-ghost" onClick={() => setPickerOpen(true)} disabled={busy || !editable || !samples?.length}>Choose demo documents</button>
            <button className="btn btn-ghost" onClick={resetDemo} disabled={busy}><RotateCcw size={14} /> Restart demo</button>
          </section>
        </aside>
      </div>

      {pickerOpen && samples && (
        <div className="modal" role="dialog" aria-label="Demo documents" onClick={() => setPickerOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h2>Demo documents</h2>
            <p className="muted small">Synthetic documents only. No real personal data.</p>
            {samples.map((s) => (
              <div key={s.key} className="scenario">
                <div><strong>{s.title}</strong><div className="muted small">{s.description}</div></div>
                <div className="row">
                  <button className="btn btn-primary" onClick={() => void useScenario(s)}>Upload documents</button>
                  {s.key === "blurry" && (
                    <button className="btn btn-ghost" onClick={() => { setPickerOpen(false); void useSample(s.key, `${currentDoc}_retake`); }}>Upload sharp retake</button>
                  )}
                </div>
              </div>
            ))}
            <button className="btn btn-ghost" onClick={() => setPickerOpen(false)}>Close</button>
          </div>
        </div>
      )}
    </Layout>
  );
}

function statusBanner(status: string): string {
  return ({
    under_review: "With a bank reviewer. This page updates automatically when a decision is made.",
    info_requested: "The reviewer asked for more information. Update your details or documents, then submit again.",
    approved: "Approved by a bank reviewer.",
    rejected: "A bank reviewer has decided on this application.",
  } as Record<string, string>)[status] ?? "";
}

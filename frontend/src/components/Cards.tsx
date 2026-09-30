import { CheckCircle2, FileUp, ShieldCheck, Sparkles } from "lucide-react";
import { useRef } from "react";
import type { Card, ExtractedField } from "../api/types";

export interface CardHandlers {
  busy: boolean;
  onAction: (action: Record<string, unknown>) => void;
  onFile: (docType: string, file: File) => void;
  onSamples?: () => void;
}

function ConfidenceChip({ field }: { field: ExtractedField }) {
  if (field.source === "llm_fallback") return <span className="chip chip-warn">AI fallback · verify</span>;
  if (field.source === "ocr_checksum_failed") return <span className="chip chip-warn">checksum failed</span>;
  if (field.confidence == null) return null;
  const pct = Math.round(field.confidence * 100);
  return <span className={`chip ${field.confidence >= 0.8 ? "chip-ok" : "chip-warn"}`}>{pct}%</span>;
}

function FieldTable({ fields }: { fields: ExtractedField[] }) {
  return (
    <dl className="kv">
      {fields.map((f) => (
        <div key={f.key} className="kv-row">
          <dt>{f.label}</dt>
          <dd>{f.value} <ConfidenceChip field={f} /></dd>
        </div>
      ))}
    </dl>
  );
}

export function CardView({ card, active, h }: { card: Card; active: boolean; h: CardHandlers }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const disabled = !active || h.busy;

  switch (card.type) {
    case "upload_request":
      return (
        <div className="card">
          <div className="card-title"><FileUp size={16} /> {card.label}</div>
          <ul className="tips">{card.tips.map((t) => <li key={t}>{t}</li>)}</ul>
          {active && (
            <div className="row">
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,application/pdf" hidden data-testid="file-input"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) h.onFile(card.doc_type, f); e.target.value = ""; }} />
              <button className="btn btn-primary" disabled={h.busy} onClick={() => fileRef.current?.click()}>Choose a photo or PDF</button>
              {h.onSamples && <button className="btn btn-ghost" disabled={h.busy} onClick={h.onSamples}>Use a demo document</button>}
            </div>
          )}
          {card.remaining.length > 1 && <div className="muted small">Still to come: {card.remaining.slice(1).join(", ")}</div>}
        </div>
      );

    case "extraction":
      return (
        <div className="card">
          <div className="card-title"><Sparkles size={16} /> Read from your {card.label}</div>
          <FieldTable fields={card.fields} />
          {card.missing.length > 0 && <div className="muted small">Could not read: {card.missing.join(", ")}</div>}
        </div>
      );

    case "confirm":
      return (
        <div className="card">
          <div className="card-title"><ShieldCheck size={16} /> Please confirm your {card.label.toLowerCase()}</div>
          <div className="options">
            {card.options.map((o) => (
              <button key={o.value} className="option" disabled={disabled}
                onClick={() => h.onAction({ type: "confirm", field: card.field, value: o.value })}>
                <strong>{o.value}</strong><span className="muted small">from your {o.source}</span>
              </button>
            ))}
          </div>
          <div className="muted small">None of these? Type the correct {card.label.toLowerCase()} below.</div>
        </div>
      );

    case "field": {
      const answer = (value: string) => h.onAction({ type: "answer", field: card.field, value });
      const buttons = card.kind === "bool" ? ["Yes", "No"] : card.kind === "choice" ? card.choices : [];
      return (
        <div className="card">
          <div className="options inline">
            {buttons.map((b) => <button key={b} className="option" disabled={disabled} onClick={() => answer(b)}>{b}</button>)}
            {card.optional && <button className="option" disabled={disabled} onClick={() => answer("Skip")}>Skip</button>}
          </div>
          {buttons.length === 0 && !card.optional && <div className="muted small">Type your answer below.</div>}
          {buttons.length === 0 && card.optional && <div className="muted small">Type a name below, or skip.</div>}
        </div>
      );
    }

    case "ready":
      return (
        <div className="card">
          <div className="card-title"><CheckCircle2 size={16} /> Application summary</div>
          <dl className="kv">{card.items.map((i) => <div key={i.label} className="kv-row"><dt>{i.label}</dt><dd>{i.value}</dd></div>)}</dl>
          {active && <button className="btn btn-primary" disabled={h.busy} data-testid="submit-btn" onClick={() => h.onAction({ type: "submit" })}>Submit for review</button>}
          <div className="muted small">A human reviewer makes the final decision. Nothing is approved automatically.</div>
        </div>
      );

    case "citations":
      return <div className="citations">{card.items.map((c) => <span key={c.title + c.section} className="chip chip-src">Source: {c.title.replace(/_/g, " ")} › {c.section}</span>)}</div>;

    case "submitted":
      return <div className="card card-success"><CheckCircle2 size={16} /> Submission #{card.submission_no} is with the reviewer</div>;

    case "upload_ack":
      return null;
  }
}

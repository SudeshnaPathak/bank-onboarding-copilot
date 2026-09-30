import { Check, ChevronDown, ChevronRight, Circle, Cpu } from "lucide-react";
import { useState } from "react";
import type { CaseView, TraceItem } from "../api/types";

export function ProgressRail({ steps }: { steps: CaseView["progress"] }) {
  return (
    <ol className="rail" aria-label="Application progress">
      {steps.map((s) => (
        <li key={s.key} className={`rail-step rail-${s.status}`}>
          <span className="rail-icon">{s.status === "done" ? <Check size={14} /> : <Circle size={10} />}</span>
          {s.label}
        </li>
      ))}
    </ol>
  );
}

export function AgentActivity({ trace }: { trace: TraceItem[] }) {
  const [open, setOpen] = useState(true);
  return (
    <section className="panel">
      <button className="panel-head" onClick={() => setOpen(!open)}>
        <Cpu size={15} /> Agent activity {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <ul className="trace">
          {trace.length === 0 && <li className="muted small">Steps taken by the agents appear here.</li>}
          {trace.map((t, i) => <li key={i}><code>{t.node}</code> {t.detail}</li>)}
        </ul>
      )}
    </section>
  );
}

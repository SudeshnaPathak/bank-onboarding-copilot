import { AlertTriangle, ShieldAlert } from "lucide-react";
import type { Analysis, Flag, Severity } from "../api/types";

export function SeverityBadge({ s }: { s: Severity }) {
  return <span className={`sev sev-${s}`}>{s}</span>;
}

const BAND_LABEL = { clean: "No inconsistencies", review: "Needs a closer look", attention: "Needs careful review" } as const;

export function ScoreDial({ score, band }: { score: number; band: Analysis["band"] }) {
  const r = 42, c = 2 * Math.PI * r;
  return (
    <div className={`dial dial-${band}`} role="img" aria-label={`Consistency score ${score} out of 100, ${BAND_LABEL[band]}`}>
      <svg viewBox="0 0 100 100" width="112" height="112">
        <circle cx="50" cy="50" r={r} className="dial-track" />
        <circle cx="50" cy="50" r={r} className="dial-fill" strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 50 50)" />
        <text x="50" y="55" textAnchor="middle" className="dial-num">{score}</text>
      </svg>
      <div><strong>{BAND_LABEL[band]}</strong><div className="muted small">Consistency score, not an approval prediction</div></div>
    </div>
  );
}

export function FlagList({ flags }: { flags: Flag[] }) {
  if (flags.length === 0) return <div className="ok-note">The rules found no inconsistencies across the submitted documents.</div>;
  return (
    <ul className="flags">
      {flags.map((f, i) => (
        <li key={i} className={`flag flag-${f.severity}`}>
          <div className="flag-head">
            {f.severity === "critical" ? <ShieldAlert size={16} /> : <AlertTriangle size={16} />}
            <strong>{f.title}</strong> <SeverityBadge s={f.severity} />
            {f.confirmed_by_customer && <span className="chip chip-ok">customer confirmed</span>}
            <code className="muted small">{f.code}</code>
          </div>
          <div>{f.message}</div>
        </li>
      ))}
    </ul>
  );
}

import { Bot } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ChatMessage, TraceItem } from "../api/types";
import { CardView, type CardHandlers } from "./Cards";

function Bubble({ m, isLast, h }: { m: ChatMessage; isLast: boolean; h: CardHandlers }) {
  const mine = m.role === "user";
  const withCard = m.ui && m.ui.type !== "upload_ack";
  return (
    <div className={`msg ${mine ? "msg-user" : "msg-bot"}`}>
      {!mine && <div className="avatar"><Bot size={16} /></div>}
      <div className="msg-body">
        {m.text && <div className="bubble" style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>}
        {withCard && m.ui && <CardView card={m.ui} active={isLast && !mine} h={h} />}
      </div>
    </div>
  );
}

export function ChatThread({ messages, busy, live, h }: { messages: ChatMessage[]; busy: boolean; live: TraceItem[]; h: CardHandlers }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, busy, live.length]);
  return (
    <div className="thread" role="log" aria-live="polite">
      {messages.map((m, i) => <Bubble key={m.id} m={m} isLast={i === messages.length - 1} h={h} />)}
      {busy && (
        <div className="msg msg-bot">
          <div className="avatar"><Bot size={16} /></div>
          <div className="bubble typing">
            <span className="dots"><i /><i /><i /></span>
            {live.length > 0 && <span className="muted small"> {live[live.length - 1].node}…</span>}
          </div>
        </div>
      )}
      <div ref={end} />
    </div>
  );
}

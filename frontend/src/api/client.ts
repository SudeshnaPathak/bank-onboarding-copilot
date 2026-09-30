import type { CaseView, DemoScenario, QueueRow, ReviewDetail, StreamEvent, User } from "./types";

const TOKEN_KEY = "onboarding.token";
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const t = tokenStore.get();
  return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...extra };
}

async function errorFrom(res: Response): Promise<ApiError> {
  let msg = res.statusText;
  try {
    const body = await res.json();
    msg = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ") : msg;
  } catch { /* non-JSON error body */ }
  return new ApiError(res.status, msg);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method, headers: headers(body ? { "Content-Type": "application/json" } : {}), body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<T>;
}

/** Reads a Server-Sent Events response from a POST (EventSource cannot POST). */
export async function* readEvents(res: Response): AsyncGenerator<StreamEvent> {
  if (!res.ok || !res.body) throw await errorFrom(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (event && data) yield { event, data: JSON.parse(data) } as StreamEvent;
    }
  }
}

export const api = {
  login: (email: string, password: string) => request<{ token: string; user: User }>("POST", "/auth/login", { email, password }),
  me: () => request<User>("GET", "/auth/me"),

  openCase: () => request<CaseView>("POST", "/cases"),
  getCase: (id: string) => request<CaseView>("GET", `/cases/${id}`),
  chat: async (id: string, payload: { text?: string; action?: Record<string, unknown> }) =>
    readEvents(await fetch(`/api/cases/${id}/chat`, { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(payload) })),
  upload: async (id: string, docType: string, file: Blob, name = "document") => {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file, name);
    return readEvents(await fetch(`/api/cases/${id}/documents`, { method: "POST", headers: headers(), body: form }));
  },

  demoSamples: () => request<DemoScenario[]>("GET", "/demo/samples"),
  demoSampleBlob: async (scenario: string, docType: string) => {
    const res = await fetch(`/api/demo/samples/${scenario}/${docType}`, { headers: headers() });
    if (!res.ok) throw await errorFrom(res);
    return res.blob();
  },
  demoReset: () => request<{ ok: boolean }>("POST", "/demo/reset"),

  queue: () => request<QueueRow[]>("GET", "/review/queue"),
  reviewDetail: (id: string) => request<ReviewDetail>("GET", `/review/${id}`),
  documentImage: async (caseId: string, docId: string, page = 0) => {
    const res = await fetch(`/api/review/${caseId}/documents/${docId}/image?page=${page}`, { headers: headers() });
    if (!res.ok) throw await errorFrom(res);
    return URL.createObjectURL(await res.blob());
  },
  decide: (id: string, action: string, note: string) => request<{ status: string }>("POST", `/review/${id}/decide`, { action, note }),
  verifyAudit: () => request<{ valid: boolean; entries: number }>("GET", "/audit/verify"),
  health: () => request<{ llm: string; ocr: string; demo_mode: boolean }>("GET", "/health"),
};

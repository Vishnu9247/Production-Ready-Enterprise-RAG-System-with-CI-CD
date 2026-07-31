import type {
  Answer,
  ChatSession,
  IngestResponse,
  QueryRequest,
  SessionHistory,
} from "./types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  let message = `Request failed with status ${response.status}`;
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) message = payload.detail;
  } catch {
    // Keep the status-based fallback for non-JSON errors.
  }
  throw new Error(message);
}

export async function uploadDocument(
  file: File,
  namespace: string,
): Promise<IngestResponse> {
  const body = new FormData();
  body.append("file", file);
  const query = namespace.trim()
    ? `?namespace=${encodeURIComponent(namespace.trim())}`
    : "";
  return parseResponse<IngestResponse>(
    await fetch(`${API_BASE_URL}/v1/documents${query}`, { method: "POST", body }),
  );
}

export async function createSession(
  name: string,
  namespace: string,
): Promise<ChatSession> {
  return parseResponse<ChatSession>(
    await fetch(`${API_BASE_URL}/v1/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, namespace }),
    }),
  );
}

export async function getSessionHistory(
  sessionId: string,
): Promise<SessionHistory> {
  return parseResponse<SessionHistory>(
    await fetch(`${API_BASE_URL}/v1/sessions/${encodeURIComponent(sessionId)}`),
  );
}

export async function askQuestion(request: QueryRequest): Promise<Answer> {
  return parseResponse<Answer>(
    await fetch(`${API_BASE_URL}/v1/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }),
  );
}

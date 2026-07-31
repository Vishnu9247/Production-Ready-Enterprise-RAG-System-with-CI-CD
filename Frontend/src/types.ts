export interface IngestResponse {
  document_id: string;
  document_name: string;
  chunks_upserted: number;
  namespace: string;
  storage_uri: string | null;
}

export interface Reference {
  number: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_numbers: number[];
  score: number;
  storage_uri: string;
}

export interface Answer {
  session_id: string;
  query: string;
  resolved_query: string;
  answer: string;
  reason: string;
  references: Reference[];
}

export interface QueryRequest {
  session_id: string;
  query: string;
  search_mode: "hybrid" | "semantic" | "keyword";
}

export interface ChatSession {
  session_id: string;
  name: string;
  namespace: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  resolved_query: string | null;
  reason: string | null;
  references: Reference[];
  created_at: string;
}

export interface SessionHistory {
  session: ChatSession;
  messages: ChatMessage[];
}

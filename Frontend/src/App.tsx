import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  askQuestion,
  createSession,
  getSessionHistory,
  uploadDocument,
} from "./api";
import type {
  ChatMessage,
  ChatSession,
  IngestResponse,
  QueryRequest,
} from "./types";

type Page = "upload" | "query";
const STORED_SESSION_KEY = "enterprise-rag-session";

function App() {
  const [page, setPage] = useState<Page>("upload");
  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" type="button" onClick={() => setPage("upload")}>
          <span className="brand-mark">R</span>
          <span><strong>Enterprise RAG</strong><small>Document intelligence</small></span>
        </button>
        <nav aria-label="Primary navigation">
          <button className={page === "upload" ? "nav-button active" : "nav-button"} type="button" onClick={() => setPage("upload")}>
            Upload documents
          </button>
          <button className={page === "query" ? "nav-button active" : "nav-button"} type="button" onClick={() => setPage("query")}>
            Query documents
          </button>
        </nav>
      </header>
      <main>{page === "upload" ? <UploadPage /> : <QueryPage />}</main>
    </div>
  );
}

function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [namespace, setNamespace] = useState("default");
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    if (!file) return setError("Choose a PDF before uploading.");
    setError("");
    setResult(null);
    setIsUploading(true);
    try {
      setResult(await uploadDocument(file, namespace));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section className="page narrow-page">
      <div className="page-heading">
        <p className="eyebrow">Knowledge base</p>
        <h1>Upload a document</h1>
        <p>Add a PDF to your searchable document collection.</p>
      </div>
      <form className="panel upload-panel" onSubmit={handleUpload}>
        <label className="file-drop">
          <input type="file" accept="application/pdf,.pdf" onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setResult(null);
            setError("");
          }} />
          <span className="file-icon" aria-hidden="true">PDF</span>
          <strong>{file ? file.name : "Choose a PDF"}</strong>
          <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "Click to select a document"}</small>
        </label>
        <label className="field">
          <span>Namespace</span>
          <input value={namespace} onChange={(event) => setNamespace(event.target.value)} placeholder="default" />
          <small>Use the same namespace when creating a query session.</small>
        </label>
        {error && <div className="notice error">{error}</div>}
        {result && <div className="notice success">
          <strong>{result.document_name} is ready.</strong>
          <span>{result.chunks_upserted} chunks indexed in “{result.namespace}”.</span>
        </div>}
        <button className="primary-button" type="submit" disabled={isUploading}>
          {isUploading ? "Processing document…" : "Upload and index"}
        </button>
      </form>
    </section>
  );
}

function QueryPage() {
  const [session, setSession] = useState<ChatSession | null>(() => {
    const stored = localStorage.getItem(STORED_SESSION_KEY);
    if (!stored) return null;
    try { return JSON.parse(stored) as ChatSession; } catch { return null; }
  });

  function saveSession(created: ChatSession) {
    localStorage.setItem(STORED_SESSION_KEY, JSON.stringify(created));
    setSession(created);
  }

  function endSession() {
    localStorage.removeItem(STORED_SESSION_KEY);
    setSession(null);
  }

  return session
    ? <ChatWindow session={session} onEnd={endSession} />
    : <CreateSession onCreate={saveSession} />;
}

function CreateSession({ onCreate }: { onCreate: (session: ChatSession) => void }) {
  const [name, setName] = useState("");
  const [namespace, setNamespace] = useState("default");
  const [error, setError] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setIsCreating(true);
    try {
      onCreate(await createSession(name.trim() || "New research session", namespace.trim() || "default"));
    } catch (sessionError) {
      setError(sessionError instanceof Error ? sessionError.message : "Could not create session.");
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <section className="page narrow-page">
      <div className="page-heading">
        <p className="eyebrow">Question answering</p>
        <h1>Create a query session</h1>
        <p>Start a session before asking questions about your documents.</p>
      </div>
      <form className="panel session-panel" onSubmit={submit}>
        <label className="field"><span>Session name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Quarterly report review" /></label>
        <label className="field"><span>Document namespace</span><input value={namespace} onChange={(event) => setNamespace(event.target.value)} placeholder="default" /></label>
        {error && <div className="notice error">{error}</div>}
        <button className="primary-button" type="submit" disabled={isCreating}>
          {isCreating ? "Creating…" : "Create session"}
        </button>
      </form>
    </section>
  );
}

function ChatWindow({ session, onEnd }: { session: ChatSession; onEnd: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<QueryRequest["search_mode"]>("hybrid");
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const shortSessionId = useMemo(() => session.session_id.slice(0, 8), [session.session_id]);

  useEffect(() => {
    getSessionHistory(session.session_id)
      .then((history) => setMessages(history.messages))
      .catch((historyError) => setError(historyError instanceof Error ? historyError.message : "Could not load session history."));
  }, [session.session_id]);

  async function refreshHistory() {
    const history = await getSessionHistory(session.session_id);
    setMessages(history.messages);
  }

  async function sendQuestion(event: FormEvent) {
    event.preventDefault();
    const query = question.trim();
    if (!query || isSending) return;
    setQuestion("");
    setError("");
    setIsSending(true);
    try {
      await askQuestion({ session_id: session.session_id, query, search_mode: mode });
      await refreshHistory();
    } catch (queryError) {
      setError(queryError instanceof Error ? queryError.message : "Query failed.");
      await refreshHistory().catch(() => undefined);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="chat-page">
      <header className="chat-header">
        <div><span className="status-dot" aria-hidden="true" /><strong>{session.name}</strong><small>Namespace: {session.namespace} · Session {shortSessionId}</small></div>
        <button className="secondary-button" type="button" onClick={onEnd}>End session</button>
      </header>
      <div className="message-list" aria-live="polite">
        {messages.length === 0 && <div className="empty-chat"><span className="empty-icon">?</span><h2>Ask your first question</h2><p>Answers will use documents indexed in “{session.namespace}”.</p></div>}
        {messages.map((message) => (
          <article className={`message ${message.role}`} key={message.message_id}>
            <div className="message-label">{message.role === "user" ? "You" : "RAG assistant"}</div>
            <p>{message.content}</p>
            {message.reason && <div className="answer-reason"><strong>Reason</strong><span>{message.reason}</span></div>}
            {message.references.length > 0 && <div className="citations">
              <strong>References</strong>
              {message.references.map((reference) => <span key={`${message.message_id}-${reference.number}`}>
                [{reference.number}] {reference.document_name || "Document"}
                {reference.page_numbers.length > 0 ? ` · p. ${reference.page_numbers.join(", ")}` : ""}
              </span>)}
            </div>}
          </article>
        ))}
        {isSending && <div className="message assistant loading-message"><span /><span /><span /></div>}
      </div>
      <div className="composer-area">
        {error && <div className="notice error">{error}</div>}
        <form className="composer" onSubmit={sendQuestion}>
          <select aria-label="Search mode" value={mode} onChange={(event) => setMode(event.target.value as QueryRequest["search_mode"])}>
            <option value="hybrid">Hybrid</option><option value="semantic">Semantic</option><option value="keyword">Keyword</option>
          </select>
          <input aria-label="Question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question about your documents…" />
          <button className="send-button" type="submit" disabled={!question.trim() || isSending}>Send</button>
        </form>
      </div>
    </section>
  );
}

export default App;

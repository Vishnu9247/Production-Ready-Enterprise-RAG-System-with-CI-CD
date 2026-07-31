import unittest
from datetime import datetime, timezone

from Backend.rag_app.agents.models import (
    GroundedAnswerDraft,
    QueryAnalysis,
    RerankResult,
    RewrittenQuery,
)
from Backend.rag_app.agents.workflow import QueryWorkflow
from Backend.rag_app.core.config import Settings
from Backend.rag_app.core.schemas import ConversationMessage, SearchResult


class FakeAzure:
    def complete_structured(self, messages, response_model, **kwargs):
        if response_model is QueryAnalysis:
            return QueryAnalysis(
                is_complete=False,
                history_messages_needed=2,
                explanation="The subject is implicit.",
            )
        if response_model is RewrittenQuery:
            return RewrittenQuery(query="What was Acme's 2025 revenue?")
        if response_model is RerankResult:
            return RerankResult(ranked_chunk_ids=["chunk-2", "chunk-1"])
        if response_model is GroundedAnswerDraft:
            return GroundedAnswerDraft(
                answer="Acme's 2025 revenue was $10 million [1].",
                reason="The revenue table supplies the figure.",
                cited_reference_numbers=[1],
            )
        raise AssertionError(response_model)


class FakeConversations:
    def list_messages(self, session_id, *, limit):
        self.limit = limit
        now = datetime.now(timezone.utc)
        return [
            ConversationMessage(
                message_id="m1",
                session_id=session_id,
                role="user",
                content="Tell me about Acme.",
                created_at=now,
            ),
            ConversationMessage(
                message_id="m2",
                session_id=session_id,
                role="assistant",
                content="What year should I use?",
                created_at=now,
            ),
        ]


class FakeRetriever:
    def search(self, query, **kwargs):
        self.query = query
        duplicate = SearchResult(
            chunk_id="chunk-duplicate",
            score=0.8,
            text="Overview",
            metadata={"document_name": "overview.pdf"},
        )
        return [
            SearchResult(
                chunk_id="chunk-1",
                score=0.9,
                text="Overview",
                metadata={"document_name": "overview.pdf"},
            ),
            duplicate,
            SearchResult(
                chunk_id="chunk-2",
                score=0.85,
                text="Revenue was $10 million.",
                metadata={"document_name": "annual-report.pdf", "page_numbers": [7]},
            ),
        ]


class QueryWorkflowTests(unittest.TestCase):
    def test_incomplete_query_uses_llm_selected_history_and_grounded_references(self):
        conversations = FakeConversations()
        retriever = FakeRetriever()
        workflow = QueryWorkflow(
            Settings(_env_file=None),
            FakeAzure(),
            conversations,
            retriever,
        )
        result = workflow.invoke(
            {
                "session_id": "session-1",
                "namespace": "default",
                "query": "What about its revenue?",
                "search_mode": "hybrid",
                "top_k": 5,
            }
        )

        self.assertEqual(conversations.limit, 2)
        self.assertEqual(retriever.query, "What was Acme's 2025 revenue?")
        self.assertEqual(len(result["context"]), 2)
        self.assertEqual(result["references"][0].document_name, "annual-report.pdf")
        self.assertEqual(result["references"][0].page_numbers, [7])


if __name__ == "__main__":
    unittest.main()

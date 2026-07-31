import unittest
from datetime import datetime, timezone

from Backend.rag_app.core.config import Settings
from Backend.rag_app.core.schemas import ConversationMessage, Reference, SessionResponse
from Backend.rag_app.rag_pipeline.service import RAGService


class FakeConversations:
    def get_session(self, session_id):
        now = datetime.now(timezone.utc)
        return SessionResponse(
            session_id=session_id,
            name="Test",
            namespace="finance",
            created_at=now,
            updated_at=now,
        )

    def append_exchange(self, **kwargs):
        now = datetime.now(timezone.utc)
        return [
            ConversationMessage(
                message_id="user-message",
                session_id=kwargs["session_id"],
                role="user",
                content=kwargs["query"],
                resolved_query=kwargs["resolved_query"],
                created_at=now,
            ),
            ConversationMessage(
                message_id="assistant-message",
                session_id=kwargs["session_id"],
                role="assistant",
                content=kwargs["answer"],
                resolved_query=kwargs["resolved_query"],
                reason=kwargs["reason"],
                references=kwargs["references"],
                created_at=now,
            ),
        ]


class FakeWorkflow:
    def invoke(self, state):
        self.state = state
        return state | {
            "resolved_query": "How did revenue change?",
            "answer": "Revenue increased by ten percent [1].",
            "reason": "The cited report states a ten percent increase.",
            "references": [
                Reference(
                    number=1,
                    chunk_id="doc_1_chunk_1",
                    document_id="doc_1",
                    document_name="report.pdf",
                    page_numbers=[3],
                    score=0.91,
                )
            ],
        }


class FakeStore:
    def upsert_history_messages(self, messages):
        self.messages = messages
        return len(messages)


class RAGServiceTests(unittest.TestCase):
    def test_answer_persists_history_and_contains_reference_details(self) -> None:
        conversations = FakeConversations()
        workflow = FakeWorkflow()
        store = FakeStore()
        service = RAGService(
            Settings(_env_file=None),
            azure=object(),
            vector_store=store,
            conversations=conversations,
            query_workflow=workflow,
        )
        result = service.answer("session-1", "And revenue?")

        self.assertIn("[1]", result.answer)
        self.assertEqual(result.references[0].page_numbers, [3])
        self.assertEqual(result.references[0].document_name, "report.pdf")
        self.assertEqual(workflow.state["namespace"], "finance")
        self.assertEqual(len(store.messages), 2)


if __name__ == "__main__":
    unittest.main()

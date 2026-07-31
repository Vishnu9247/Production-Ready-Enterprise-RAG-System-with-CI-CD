"""Agent that makes a standalone query from the current message and history."""

from ..core.config import Settings
from ..database.conversation_repository import ConversationRepository
from ..embedding_generation.service import AzureOpenAIService
from .models import QueryAnalysis, RewrittenQuery
from .state import QueryWorkflowState


class QueryContextAgent:
    def __init__(
        self,
        settings: Settings,
        azure: AzureOpenAIService,
        conversations: ConversationRepository,
    ) -> None:
        self.settings = settings
        self.azure = azure
        self.conversations = conversations

    def analyze(self, state: QueryWorkflowState) -> dict:
        analysis = self.azure.complete_structured(
            [
                {
                    "role": "system",
                    "content": (
                        "Decide whether the user message is a standalone search query. "
                        "A query is incomplete when it relies on omitted subjects, pronouns, "
                        "or earlier conversation context. If incomplete, choose how many prior "
                        "messages are needed to resolve it. Choose the smallest useful number. "
                        f"The maximum is {self.settings.history_max_messages}. "
                        "Do not answer the query."
                    ),
                },
                {"role": "user", "content": state["query"]},
            ],
            QueryAnalysis,
        )
        needed = min(
            max(analysis.history_messages_needed, 0),
            self.settings.history_max_messages,
        )
        if not analysis.is_complete and needed == 0:
            needed = self.settings.history_default_messages
        return {
            "is_complete": analysis.is_complete,
            "history_messages_needed": needed,
            "resolved_query": state["query"] if analysis.is_complete else "",
        }

    def rewrite(self, state: QueryWorkflowState) -> dict:
        history = self.conversations.list_messages(
            state["session_id"],
            limit=state["history_messages_needed"],
        )
        if not history:
            return {"history": [], "resolved_query": state["query"]}
        transcript = "\n".join(
            f"{message.role.upper()}: {message.content}" for message in history
        )
        rewritten = self.azure.complete_structured(
            [
                {
                    "role": "system",
                    "content": (
                        "Rewrite the current message as one complete, standalone query for "
                        "document retrieval. Use only necessary context from the transcript. "
                        "Preserve the user's intent and do not answer the query."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Conversation:\n{transcript}\n\nCurrent message:\n{state['query']}",
                },
            ],
            RewrittenQuery,
        )
        return {"history": history, "resolved_query": rewritten.query.strip()}

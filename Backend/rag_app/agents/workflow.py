"""LangGraph orchestration for the bounded multi-agent query workflow."""

from langgraph.graph import END, START, StateGraph

from ..core.config import Settings
from ..database.conversation_repository import ConversationRepository
from ..embedding_generation.service import AzureOpenAIService
from ..retrieval.hybrid import HybridRetriever
from .answer import GroundedAnswerAgent
from .context_quality import ContextQualityAgent
from .query_context import QueryContextAgent
from .retrieval import RetrievalAgent
from .state import QueryWorkflowState


class QueryWorkflow:
    def __init__(
        self,
        settings: Settings,
        azure: AzureOpenAIService,
        conversations: ConversationRepository,
        retriever: HybridRetriever,
    ) -> None:
        query_context = QueryContextAgent(settings, azure, conversations)
        retrieval = RetrievalAgent(settings, retriever)
        context_quality = ContextQualityAgent(settings, azure)
        answer = GroundedAnswerAgent(azure)

        graph = StateGraph(QueryWorkflowState)
        graph.add_node("analyze_query", query_context.analyze)
        graph.add_node("rewrite_query", query_context.rewrite)
        graph.add_node("retrieve_documents", retrieval.retrieve)
        graph.add_node("curate_context", context_quality.deduplicate_and_rerank)
        graph.add_node("compose_answer", answer.compose)
        graph.add_edge(START, "analyze_query")
        graph.add_conditional_edges(
            "analyze_query",
            self._query_route,
            {"rewrite": "rewrite_query", "retrieve": "retrieve_documents"},
        )
        graph.add_edge("rewrite_query", "retrieve_documents")
        graph.add_edge("retrieve_documents", "curate_context")
        graph.add_edge("curate_context", "compose_answer")
        graph.add_edge("compose_answer", END)
        self.graph = graph.compile()

    def invoke(self, state: QueryWorkflowState) -> QueryWorkflowState:
        return self.graph.invoke(state)

    @staticmethod
    def _query_route(state: QueryWorkflowState) -> str:
        return "retrieve" if state["is_complete"] else "rewrite"

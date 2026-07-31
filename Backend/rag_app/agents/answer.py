"""Agent that composes a grounded answer from curated context."""

import re

from ..core.schemas import Reference, SearchResult
from ..embedding_generation.service import AzureOpenAIService
from .models import GroundedAnswerDraft
from .state import QueryWorkflowState


class GroundedAnswerAgent:
    def __init__(self, azure: AzureOpenAIService) -> None:
        self.azure = azure

    def compose(self, state: QueryWorkflowState) -> dict:
        context = state.get("context", [])
        if not context:
            return {
                "answer": "I do not know based on the indexed documents.",
                "reason": "No relevant document evidence was retrieved.",
                "references": [],
            }
        blocks = "\n\n".join(
            f"[{number}] {source.text}" for number, source in enumerate(context, start=1)
        )
        draft = self.azure.complete_structured(
            [
                {
                    "role": "system",
                    "content": (
                        "Answer using only the supplied document context. If the evidence is "
                        "insufficient, explicitly say so. Do not invent facts or sources. "
                        "The answer must be direct and may use inline reference markers like [1]. "
                        "The reason must be a concise evidence summary, not private chain-of-thought. "
                        "Return the reference numbers actually used."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{state['resolved_query']}\n\n"
                        f"Document context:\n{blocks}"
                    ),
                },
            ],
            GroundedAnswerDraft,
        )
        declared_numbers = {
            number
            for number in draft.cited_reference_numbers
            if 1 <= number <= len(context)
        }
        mentioned_numbers = {
            int(number)
            for number in re.findall(r"\[(\d+)\]", draft.answer)
            if 1 <= int(number) <= len(context)
        }
        valid_numbers = declared_numbers | mentioned_numbers
        if not valid_numbers:
            valid_numbers = set(range(1, len(context) + 1))
        references = [
            self._reference(number, source)
            for number, source in enumerate(context, start=1)
            if number in valid_numbers
        ]
        return {
            "answer": draft.answer.strip(),
            "reason": draft.reason.strip(),
            "references": references,
        }

    @staticmethod
    def _reference(number: int, source: SearchResult) -> Reference:
        raw_pages = source.metadata.get("page_numbers", [])
        pages: list[int] = []
        for page in raw_pages if isinstance(raw_pages, list) else [raw_pages]:
            try:
                pages.append(int(float(page)))
            except (TypeError, ValueError):
                continue
        return Reference(
            number=number,
            chunk_id=source.chunk_id,
            document_id=str(source.metadata.get("document_id", "")),
            document_name=str(source.metadata.get("document_name", "")),
            page_numbers=pages,
            score=source.score,
            storage_uri=str(source.metadata.get("storage_uri", "")),
        )

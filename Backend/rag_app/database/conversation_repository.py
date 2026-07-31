"""Durable PostgreSQL storage for conversation sessions and messages."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings
from ..core.exceptions import SessionNotFoundError
from ..core.schemas import (
    ConversationMessage,
    Reference,
    SessionResponse,
)
from .models import ConversationMessageRecord, ConversationSessionRecord
from .session import create_session_factory


class ConversationRepository:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.session_factory = session_factory or create_session_factory(settings)

    def create_session(self, name: str, namespace: str) -> SessionResponse:
        record = ConversationSessionRecord(
            session_id=str(uuid4()),
            name=name.strip(),
            namespace=namespace.strip(),
        )
        with self.session_factory.begin() as database:
            database.add(record)
            database.flush()
            database.refresh(record)
        return self._session_model(record)

    def get_session(self, session_id: str) -> SessionResponse:
        with self.session_factory() as database:
            record = database.get(ConversationSessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(f"Session '{session_id}' was not found")
            return self._session_model(record)

    def delete_session(self, session_id: str) -> None:
        with self.session_factory.begin() as database:
            database.execute(
                delete(ConversationSessionRecord).where(
                    ConversationSessionRecord.session_id == session_id
                )
            )

    def list_messages(self, session_id: str, *, limit: int) -> list[ConversationMessage]:
        self.get_session(session_id)
        statement = (
            select(ConversationMessageRecord)
            .where(ConversationMessageRecord.session_id == session_id)
            .order_by(
                ConversationMessageRecord.created_at.desc(),
                ConversationMessageRecord.message_id.desc(),
            )
            .limit(limit)
        )
        with self.session_factory() as database:
            records = list(database.scalars(statement))
        return [self._message_model(record) for record in reversed(records)]

    def append_exchange(
        self,
        *,
        session_id: str,
        query: str,
        resolved_query: str,
        answer: str,
        reason: str,
        references: list[Reference],
    ) -> list[ConversationMessage]:
        exchange_time = datetime.now(timezone.utc)
        user_record = ConversationMessageRecord(
            message_id=str(uuid4()),
            session_id=session_id,
            role="user",
            content=query,
            resolved_query=resolved_query,
            attributes={},
            created_at=exchange_time,
        )
        assistant_record = ConversationMessageRecord(
            message_id=str(uuid4()),
            session_id=session_id,
            role="assistant",
            content=answer,
            resolved_query=resolved_query,
            attributes={
                "reason": reason,
                "references": [reference.model_dump(mode="json") for reference in references],
            },
            created_at=exchange_time + timedelta(microseconds=1),
        )
        with self.session_factory.begin() as database:
            session_record = database.get(ConversationSessionRecord, session_id)
            if session_record is None:
                raise SessionNotFoundError(f"Session '{session_id}' was not found")
            database.add_all([user_record, assistant_record])
            session_record.updated_at = exchange_time
            database.flush()
            database.refresh(user_record)
            database.refresh(assistant_record)
        return [self._message_model(user_record), self._message_model(assistant_record)]

    @staticmethod
    def _session_model(record: ConversationSessionRecord) -> SessionResponse:
        return SessionResponse(
            session_id=record.session_id,
            name=record.name,
            namespace=record.namespace,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _message_model(record: ConversationMessageRecord) -> ConversationMessage:
        metadata = dict(record.attributes or {})
        return ConversationMessage(
            message_id=record.message_id,
            session_id=record.session_id,
            role=record.role,
            content=record.content,
            resolved_query=record.resolved_query,
            reason=metadata.get("reason"),
            references=[
                Reference.model_validate(reference)
                for reference in metadata.get("references", [])
            ],
            created_at=record.created_at,
        )

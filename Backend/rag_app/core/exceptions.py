"""Application exceptions that do not depend on the web framework."""


class UnsupportedDocumentTypeError(ValueError):
    """Raised when ingestion receives an unsupported document type."""


class SessionNotFoundError(LookupError):
    """Raised when a conversation session does not exist."""

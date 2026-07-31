"""Application exceptions that do not depend on the web framework."""


class UnsupportedDocumentTypeError(ValueError):
    """Raised when ingestion receives an unsupported document type."""

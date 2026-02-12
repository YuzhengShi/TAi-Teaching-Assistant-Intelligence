"""
Exception hierarchy for TAi.
"""


class TAiError(Exception):
    """Base exception for all TAi errors."""
    pass


class SafetyError(TAiError):
    """Base exception for safety-related errors."""
    pass


class ConsentRequiredError(SafetyError):
    """Raised when student consent is required but not granted."""
    pass


class SecurityViolationError(SafetyError):
    """Raised when a security violation is detected."""
    pass


class FERPAComplianceError(SafetyError):
    """Raised when FERPA compliance requirements are violated."""
    pass


class CircuitBreakerOpenError(TAiError):
    """Raised when circuit breaker is open and operation is blocked."""
    pass


class GraphConnectionError(TAiError):
    """Raised when Neo4j connection fails."""
    pass


class GraphQueryError(TAiError):
    """Raised when a graph query fails."""
    pass


class ExtractionError(TAiError):
    """Raised when entity/relationship extraction fails."""
    pass


class RetrievalError(TAiError):
    """Raised when retrieval operation fails."""
    pass


class SessionError(TAiError):
    """Raised when session operation fails."""
    pass


class MemoryError(TAiError):
    """Raised when memory operation fails."""
    pass

"""Neo4j data-access exceptions shared by the API layer."""


class Neo4jServiceError(RuntimeError):
    """Base class for failures in the Neo4j data-access layer."""


class Neo4jConnectionError(Neo4jServiceError):
    """The driver cannot establish or retain a database connection."""


class Neo4jQueryError(Neo4jServiceError):
    """Neo4j rejected a query or failed while executing it."""


class Neo4jQueryTimeoutError(Neo4jQueryError):
    """A query exceeded its configured server-side timeout."""

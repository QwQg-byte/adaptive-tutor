"""Exceptions raised by the synchronous Neo4j tooling connector."""


class Neo4jConnectorError(RuntimeError):
    """Base class for offline Neo4j connector failures."""


class Neo4jConnectionError(Neo4jConnectorError):
    """The connector cannot establish or retain a database connection."""


class Neo4jQueryError(Neo4jConnectorError):
    """Neo4j rejected a query or failed while executing it."""


class Neo4jQueryTimeoutError(Neo4jQueryError):
    """A query exceeded its configured server-side timeout."""

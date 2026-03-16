"""
PostgreSQL Connection Pooling Module

Implements a thread-safe connection pool to manage database connections.
Replaces ad-hoc psycopg2.connect() calls with pooled connections.

Usage:
    from db import get_connection, release_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM table")
        result = cur.fetchall()
        cur.close()
    finally:
        release_connection(conn)
"""

import os
import psycopg2
from psycopg2 import pool
from typing import Optional

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_connection_pool: Optional[pool.ThreadedConnectionPool] = None


def get_pool() -> pool.ThreadedConnectionPool:
    """Get or initialize the connection pool.

    Returns:
        ThreadedConnectionPool: A connection pool with 2-20 concurrent connections.

    Raises:
        ValueError: If DATABASE_URL is not set.
    """
    global _connection_pool

    if _connection_pool is None:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")

        _connection_pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=DATABASE_URL,
        )

    return _connection_pool


def get_connection() -> psycopg2.extensions.connection:
    """Get a connection from the pool.

    Returns:
        psycopg2.extensions.connection: A database connection from the pool.

    Raises:
        psycopg2.pool.PoolError: If no connection is available within timeout.
    """
    return get_pool().getconn()


def release_connection(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool.

    Args:
        conn: The connection to release back to the pool.
    """
    if conn is not None:
        try:
            get_pool().putconn(conn)
        except Exception:
            # Connection may already be closed or in bad state
            try:
                conn.close()
            except Exception:
                pass


def close_pool() -> None:
    """Close all connections in the pool.

    Call this on application shutdown.
    """
    global _connection_pool

    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None

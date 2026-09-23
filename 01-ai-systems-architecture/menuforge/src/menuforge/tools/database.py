"""SQLAlchemy MenuItem model and session setup.

Owns the engine, the session factory, and the one table. Deliberately knows
nothing about `menuforge.schemas` — persistence has no business knowing the shape
the LLM returns. `menuforge.main` owns the mapping between the two.

Session lifecycle is the caller's job: `get_session()` hands back an open session
and the caller closes it in a `finally`.
"""

from __future__ import annotations

import os

from sqlalchemy import JSON, Engine, Float, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://menuforge:menuforge@localhost:5432/menuforge"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """Declarative base for every menuforge table."""


class MenuItem(Base):
    """A single extracted menu item, as persisted.

    Mirrors `MenuItemSchema` field-for-field today, but is free to diverge: the
    two are mapped explicitly in `menuforge.main` rather than coupled.
    """

    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    modifiers: Mapped[list[str]] = mapped_column(JSON, default=list)


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use.

    Built lazily rather than at import time so that tests can point
    ``DATABASE_URL`` at a throwaway database before the first call.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    return _engine


def get_session() -> Session:
    """Return a new open session. The caller is responsible for closing it."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory()


def init_db() -> None:
    """Create any missing tables.

    Called from the API startup hook. Sufficient while there is no deployed data
    to preserve; see DECISIONS.md D-002 for when this has to become Alembic.
    """
    Base.metadata.create_all(bind=get_engine())


def reset_engine() -> None:
    """Drop the cached engine and session factory.

    Exists so tests can repoint ``DATABASE_URL`` between cases. Not used in
    normal operation.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

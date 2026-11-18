"""Declarative base for every table. Tables arrive from phase C1 on."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class of every mapped table; Alembic compares against its metadata."""

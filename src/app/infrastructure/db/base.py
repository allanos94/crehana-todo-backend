"""Declarative base and naming convention shared by every ORM model.

A deterministic naming convention is required because Alembic autogenerate
and `SqlAlchemyUnitOfWork`'s `IntegrityError` translation both key off exact
constraint names (design ADR-07/ADR-08).
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for every ORM model, carrying the naming-convention metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

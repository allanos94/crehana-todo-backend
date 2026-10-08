"""Tests for the `TaskList` domain entity (design ADR-02, task-lists spec:
field-validation scenarios for `name`/`description`).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.exceptions import InvalidFieldError
from app.domain.task_list import TaskList

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_create_normalizes_name_and_sets_identity() -> None:
    owner_id = uuid4()
    task_list = TaskList.create(
        owner_id=owner_id, name="  Groceries  ", description=None, now=_NOW
    )

    assert isinstance(task_list.id, UUID)
    assert task_list.owner_id == owner_id
    assert task_list.name == "Groceries"
    assert task_list.description is None
    assert task_list.created_at == _NOW
    assert task_list.updated_at == _NOW


def test_create_normalizes_blank_description_to_none() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description="   ", now=_NOW
    )

    assert task_list.description is None


def test_create_strips_description() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description="  buy milk  ", now=_NOW
    )

    assert task_list.description == "buy milk"


def test_create_rejects_blank_name_after_trim() -> None:
    with pytest.raises(InvalidFieldError) as exc_info:
        TaskList.create(owner_id=uuid4(), name="   ", description=None, now=_NOW)
    assert exc_info.value.field == "name"


def test_create_rejects_name_over_120_characters() -> None:
    with pytest.raises(InvalidFieldError):
        TaskList.create(owner_id=uuid4(), name="x" * 121, description=None, now=_NOW)


def test_create_rejects_description_over_2000_characters() -> None:
    with pytest.raises(InvalidFieldError):
        TaskList.create(
            owner_id=uuid4(), name="Groceries", description="x" * 2001, now=_NOW
        )


def test_rename_normalizes_and_updates_timestamp() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description=None, now=_NOW
    )
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task_list.rename("  Work  ", later)

    assert task_list.name == "Work"
    assert task_list.updated_at == later


def test_rename_rejects_blank_name() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description=None, now=_NOW
    )

    with pytest.raises(InvalidFieldError):
        task_list.rename("   ", _NOW)


def test_rename_rejects_name_over_120_characters() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description=None, now=_NOW
    )

    with pytest.raises(InvalidFieldError):
        task_list.rename("x" * 121, _NOW)


def test_describe_normalizes_and_updates_timestamp() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description=None, now=_NOW
    )
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task_list.describe("  buy milk  ", later)

    assert task_list.description == "buy milk"
    assert task_list.updated_at == later


def test_describe_clears_to_none_on_blank() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description="buy milk", now=_NOW
    )

    task_list.describe("   ", _NOW)

    assert task_list.description is None


def test_describe_rejects_over_2000_characters() -> None:
    task_list = TaskList.create(
        owner_id=uuid4(), name="Groceries", description=None, now=_NOW
    )

    with pytest.raises(InvalidFieldError):
        task_list.describe("x" * 2001, _NOW)

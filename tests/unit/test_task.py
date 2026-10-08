"""Tests for the `Task` domain entity (design ADR-02, tasks spec: field
validation, the strict status state machine, and the due-date rule).
"""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.exceptions import (
    DueDateInPastError,
    InvalidFieldError,
    InvalidStatusTransitionError,
)
from app.domain.task import Task
from app.domain.value_objects import Priority, TaskStatus

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_TODAY = date(2026, 1, 1)


def _create_task(**overrides: object) -> Task:
    defaults: dict[str, object] = {
        "list_id": uuid4(),
        "title": "Buy milk",
        "description": None,
        "priority": Priority.LOW,
        "due_date": None,
        "today": _TODAY,
        "now": _NOW,
    }
    defaults.update(overrides)
    return Task.create(**defaults)  # type: ignore[arg-type]


def test_create_sets_identity_and_pending_status() -> None:
    list_id = uuid4()
    task = Task.create(
        list_id=list_id,
        title="  Buy milk  ",
        description="  2% please  ",
        priority=Priority.LOW,
        due_date=None,
        today=_TODAY,
        now=_NOW,
    )

    assert isinstance(task.id, UUID)
    assert task.list_id == list_id
    assert task.title == "Buy milk"
    assert task.description == "2% please"
    assert task.status == TaskStatus.PENDING
    assert task.priority == Priority.LOW
    assert task.due_date is None
    assert task.assignee_id is None
    assert task.created_at == _NOW
    assert task.updated_at == _NOW


def test_create_rejects_blank_title() -> None:
    with pytest.raises(InvalidFieldError):
        _create_task(title="   ")


def test_create_rejects_title_over_200_characters() -> None:
    with pytest.raises(InvalidFieldError):
        _create_task(title="x" * 201)


def test_create_rejects_description_over_2000_characters() -> None:
    with pytest.raises(InvalidFieldError):
        _create_task(description="x" * 2001)


def test_create_rejects_due_date_in_the_past() -> None:
    with pytest.raises(DueDateInPastError):
        _create_task(due_date=date(2025, 12, 31), today=_TODAY)


def test_create_accepts_due_date_equal_to_today() -> None:
    task = _create_task(due_date=_TODAY, today=_TODAY)
    assert task.due_date == _TODAY


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        (TaskStatus.PENDING, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.PENDING),
        (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.IN_PROGRESS),
    ],
)
def test_change_status_allows_valid_transitions(
    source: TaskStatus, destination: TaskStatus
) -> None:
    task = _create_task()
    task.status = source
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task.change_status(destination, later)

    assert task.status == destination
    assert task.updated_at == later


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        (TaskStatus.PENDING, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.PENDING),
        (TaskStatus.PENDING, TaskStatus.PENDING),
        (TaskStatus.IN_PROGRESS, TaskStatus.IN_PROGRESS),
        (TaskStatus.DONE, TaskStatus.DONE),
    ],
)
def test_change_status_rejects_invalid_transitions(
    source: TaskStatus, destination: TaskStatus
) -> None:
    task = _create_task()
    task.status = source

    with pytest.raises(InvalidStatusTransitionError):
        task.change_status(destination, _NOW)


def test_rename_normalizes_and_updates_timestamp() -> None:
    task = _create_task()
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task.rename("  Updated title  ", later)

    assert task.title == "Updated title"
    assert task.updated_at == later


def test_rename_rejects_blank_title() -> None:
    task = _create_task()
    with pytest.raises(InvalidFieldError):
        task.rename("   ", _NOW)


def test_describe_clears_to_none_on_blank() -> None:
    task = _create_task(description="buy milk")
    task.describe("   ", _NOW)
    assert task.description is None


def test_describe_rejects_over_2000_characters() -> None:
    task = _create_task()
    with pytest.raises(InvalidFieldError):
        task.describe("x" * 2001, _NOW)


def test_set_priority_updates_timestamp() -> None:
    task = _create_task(priority=Priority.LOW)
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task.set_priority(Priority.HIGH, later)

    assert task.priority == Priority.HIGH
    assert task.updated_at == later


def test_reschedule_updates_due_date() -> None:
    task = _create_task()
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task.reschedule(date(2026, 1, 5), _TODAY, later)

    assert task.due_date == date(2026, 1, 5)
    assert task.updated_at == later


def test_reschedule_rejects_past_due_date() -> None:
    task = _create_task()
    with pytest.raises(DueDateInPastError):
        task.reschedule(date(2025, 12, 31), _TODAY, _NOW)


def test_reschedule_accepts_clearing_to_none() -> None:
    task = _create_task(due_date=_TODAY, today=_TODAY)
    task.reschedule(None, _TODAY, _NOW)
    assert task.due_date is None


def test_assign_sets_assignee_and_updates_timestamp() -> None:
    task = _create_task()
    assignee_id = uuid4()
    later = datetime(2026, 1, 2, tzinfo=UTC)

    task.assign(assignee_id, later)

    assert task.assignee_id == assignee_id
    assert task.updated_at == later


def test_assign_none_unassigns() -> None:
    task = _create_task()
    task.assign(uuid4(), _NOW)

    task.assign(None, _NOW)

    assert task.assignee_id is None

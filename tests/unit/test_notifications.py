"""Unit tests for the notification infrastructure (task-assignment spec:
fake invitation, delivered asynchronously, never a real email;
console-only, never logging secrets).
"""

import logging

import pytest
from fastapi import BackgroundTasks

from app.application.ports import TaskInvitation
from app.infrastructure.notifications.console import (
    BackgroundTaskNotifier,
    ConsoleEmailNotifier,
)

_MESSAGE = TaskInvitation(
    to_email="assignee@example.com",
    task_title="Buy milk",
    list_name="Groceries",
    invited_by_email="owner@example.com",
)


async def test_console_notifier_logs_recipient_and_task_title(
    caplog: pytest.LogCaptureFixture,
) -> None:
    notifier = ConsoleEmailNotifier()

    with caplog.at_level(logging.INFO, logger="app.notifications"):
        await notifier.send_task_invitation(_MESSAGE)

    assert any(
        "assignee@example.com" in record.message and "Buy milk" in record.message
        for record in caplog.records
    )


async def test_console_notifier_never_logs_a_secret_looking_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`TaskInvitation` never carries a secret, so this is a structural
    guard: the log line is built only from the message's own fields."""
    with caplog.at_level(logging.INFO, logger="app.notifications"):
        await ConsoleEmailNotifier().send_task_invitation(_MESSAGE)

    for record in caplog.records:
        assert "token" not in record.message.lower()
        assert "password" not in record.message.lower()


async def test_background_task_notifier_schedules_rather_than_awaits_inline() -> None:
    background_tasks = BackgroundTasks()
    delegate = ConsoleEmailNotifier()
    notifier = BackgroundTaskNotifier(background_tasks, delegate)

    await notifier.send_task_invitation(_MESSAGE)

    assert len(background_tasks.tasks) == 1

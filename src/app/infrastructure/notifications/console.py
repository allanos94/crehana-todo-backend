"""Fake email notification adapters (design ADR-12): no real email is ever
sent. `ConsoleEmailNotifier` logs one structured INFO line per invitation;
`BackgroundTaskNotifier` wraps any `NotificationService` so the HTTP
response never waits for delivery.
"""

import logging

from fastapi import BackgroundTasks

from app.application.ports import NotificationService, TaskInvitation

logger = logging.getLogger("app.notifications")


class ConsoleEmailNotifier:
    """Logs the invitation instead of sending a real email. Only
    `TaskInvitation`'s own fields are logged -- never a secret or token,
    because none ever reaches this adapter."""

    async def send_task_invitation(self, message: TaskInvitation) -> None:
        logger.info(
            "Task invitation: %s invited %s to '%s' (list '%s')",
            message.invited_by_email,
            message.to_email,
            message.task_title,
            message.list_name,
        )


class BackgroundTaskNotifier:
    """Schedules `delegate.send_task_invitation` on FastAPI's
    `BackgroundTasks` instead of awaiting it inline, so the HTTP response
    is returned without waiting for the notification to finish (design
    ADR-12, task-assignment spec)."""

    def __init__(
        self, background_tasks: BackgroundTasks, delegate: NotificationService
    ) -> None:
        self._background_tasks = background_tasks
        self._delegate = delegate

    async def send_task_invitation(self, message: TaskInvitation) -> None:
        self._background_tasks.add_task(self._delegate.send_task_invitation, message)

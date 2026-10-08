"""Domain exception hierarchy (design ADR-03).

`AppError` is the base. Category classes carry no HTTP semantics — the
domain stays framework-free — but `infrastructure/api/errors.py` maps each
category to an HTTP status code by walking `type(exc).__mro__`. Every
concrete error from the ADR-03 table is defined here up front, including
ones only used by later slices, so this module is stable and never needs to
reopen for a feature slice.
"""


class AppError(Exception):
    """Base class for every domain/application error with a stable `code`."""

    code: str = "app_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    """A requested resource does not exist, or does not belong to the actor."""


class ConflictError(AppError):
    """A request conflicts with existing state (uniqueness, invalid transition)."""


class BusinessRuleViolationError(AppError):
    """A well-formed request violates a business rule on one of its fields."""


class TaskListNotFoundError(NotFoundError):
    code = "task_list_not_found"

    def __init__(self) -> None:
        super().__init__("Task list not found")


class TaskNotFoundError(NotFoundError):
    code = "task_not_found"

    def __init__(self) -> None:
        super().__init__("Task not found")


class UserNotFoundError(NotFoundError):
    code = "user_not_found"

    def __init__(self) -> None:
        super().__init__("User not found")


class DuplicateTaskListNameError(ConflictError):
    code = "task_list_name_conflict"

    def __init__(self) -> None:
        super().__init__("A task list with this name already exists")


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_already_registered"

    def __init__(self) -> None:
        super().__init__("This email is already registered")


class InvalidStatusTransitionError(ConflictError):
    code = "invalid_status_transition"

    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"Cannot change status from {source} to {target}")
        self.source = source
        self.target = target


class InvalidFieldError(BusinessRuleViolationError):
    code = "invalid_field"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


class PasswordPolicyError(BusinessRuleViolationError):
    code = "weak_password"

    def __init__(self) -> None:
        super().__init__(
            "Password must be 8-128 characters long and contain at least "
            "one letter and one digit"
        )


class DueDateInPastError(BusinessRuleViolationError):
    code = "due_date_in_past"

    def __init__(self) -> None:
        super().__init__("Due date cannot be in the past")


class AssigneeNotFoundError(BusinessRuleViolationError):
    code = "assignee_not_found"

    def __init__(self) -> None:
        super().__init__("Assignee does not exist")

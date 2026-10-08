"""Tests for the domain exception hierarchy (design ADR-03)."""

from app.domain.exceptions import (
    AppError,
    AssigneeNotFoundError,
    BusinessRuleViolationError,
    ConflictError,
    DueDateInPastError,
    DuplicateTaskListNameError,
    EmailAlreadyRegisteredError,
    InvalidFieldError,
    InvalidStatusTransitionError,
    NotFoundError,
    PasswordPolicyError,
    TaskListNotFoundError,
    TaskNotFoundError,
    UserNotFoundError,
)


def test_category_classes_subclass_app_error() -> None:
    assert issubclass(NotFoundError, AppError)
    assert issubclass(ConflictError, AppError)
    assert issubclass(BusinessRuleViolationError, AppError)


def test_app_error_exposes_code_and_message() -> None:
    error = UserNotFoundError()
    assert isinstance(error.code, str)
    assert isinstance(error.message, str)
    assert str(error) == error.message


def test_user_not_found_is_a_not_found_error() -> None:
    error = UserNotFoundError()
    assert isinstance(error, NotFoundError)
    assert error.code == "user_not_found"


def test_task_list_not_found_is_a_not_found_error() -> None:
    assert isinstance(TaskListNotFoundError(), NotFoundError)


def test_task_not_found_is_a_not_found_error() -> None:
    assert isinstance(TaskNotFoundError(), NotFoundError)


def test_email_already_registered_is_a_conflict_error() -> None:
    error = EmailAlreadyRegisteredError()
    assert isinstance(error, ConflictError)
    assert error.code == "email_already_registered"


def test_duplicate_task_list_name_is_a_conflict_error() -> None:
    assert isinstance(DuplicateTaskListNameError(), ConflictError)


def test_invalid_status_transition_is_a_conflict_error() -> None:
    error = InvalidStatusTransitionError("pending", "done")
    assert isinstance(error, ConflictError)
    assert error.code == "invalid_status_transition"
    assert "pending" in error.message
    assert "done" in error.message


def test_invalid_field_is_a_business_rule_violation() -> None:
    error = InvalidFieldError("name", "name must not be blank")
    assert isinstance(error, BusinessRuleViolationError)
    assert error.code == "invalid_field"
    assert error.field == "name"


def test_password_policy_is_a_business_rule_violation() -> None:
    error = PasswordPolicyError()
    assert isinstance(error, BusinessRuleViolationError)
    assert error.code == "weak_password"


def test_due_date_in_past_is_a_business_rule_violation() -> None:
    assert isinstance(DueDateInPastError(), BusinessRuleViolationError)


def test_assignee_not_found_is_a_business_rule_violation() -> None:
    error = AssigneeNotFoundError()
    assert isinstance(error, BusinessRuleViolationError)
    assert error.code == "assignee_not_found"

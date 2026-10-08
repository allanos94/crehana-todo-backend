"""Shared API schemas: the error-response contract (design ADR-13)."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """One field-level validation failure."""

    field: str
    message: str
    type: str


class ErrorResponse(BaseModel):
    """The stable `{code, message[, details]}` error body every endpoint returns."""

    code: str
    message: str
    details: list[ErrorDetail] | None = None

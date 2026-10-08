"""Tests for the `Unset` PATCH sentinel (design ADR-04)."""

from app.application.common import UNSET, Unset


def test_unset_is_a_single_sentinel_value() -> None:
    assert UNSET is Unset.TOKEN


def test_unset_is_distinct_from_none() -> None:
    assert UNSET is not None

"""The `Unset` sentinel for PATCH commands (design ADR-04).

Distinguishes "the client omitted this field" (`UNSET`) from "the client
explicitly asked to clear it" (`None`). Used by later PATCH use cases
(`UpdateTaskListCommand`, `UpdateTaskCommand`, ...).
"""

import enum
from typing import Final


class Unset(enum.Enum):
    TOKEN = enum.auto()


UNSET: Final = Unset.TOKEN

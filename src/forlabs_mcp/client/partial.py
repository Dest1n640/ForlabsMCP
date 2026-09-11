"""PartialResult: the vocabulary every layer above uses to say
'here is what I got, and here is what's incomplete.'

A malformed row, or one failed call among several, becomes a warning
on the result rather than an exception that discards otherwise-valid data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class PartialResult(Generic[T]):
    data: T
    warnings: list[str] = field(default_factory=list)

    @property
    def is_partial(self) -> bool:
        return bool(self.warnings)

    @classmethod
    def ok(cls, data: T) -> PartialResult[T]:
        """Build a result with no warnings."""
        return cls(data=data, warnings=[])


def combine(results: list[PartialResult[list[T]]]) -> PartialResult[list[T]]:
    """Concatenate several list-shaped PartialResults into one.

    Used where a tool has to make several independent calls (for example,
    one homework lookup per study) and needs to union both the successful
    data and the accumulated warnings.
    """
    data: list[T] = []
    warnings: list[str] = []
    for result in results:
        data.extend(result.data)
        warnings.extend(result.warnings)
    return PartialResult(data=data, warnings=warnings)

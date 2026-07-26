
"""Module ABC + registry.

A game module is an HDL module:
  generate() = elaboration
  views()    = output ports, fanned out per role
  act()      = clocked input
  tick()     = clock, for needy modules
  inspect()  = read-only probe, delivered privately to ONE role
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import random


class Result(Enum):
    NOTHING = 0
    SOLVED = 1
    STRIKE = 2


@dataclass
class Views:
    hands: dict
    eyes: dict
    book: dict
    scope: dict | None = None

    def for_role(self, role: str) -> dict:
        return {"hands": self.hands, "eyes": self.eyes,
                "book": self.book, "scope": self.scope or {}}.get(role, {})


REGISTRY: dict[str, type["Module"]] = {}


def register(cls):
    REGISTRY[cls.id] = cls
    return cls


class Module(ABC):
    id: str = "??"
    name: str = "unnamed"
    needy: bool = False

    def __init__(self) -> None:
        self.solved = False

    @abstractmethod
    def generate(self, rng: random.Random, flags: dict) -> None:
        """Elaborate this instance from the match seed and the global edge flags."""

    @abstractmethod
    def views(self) -> Views:
        """Role-filtered state. NEVER leak cross-role fields. See tests/test_invariants.py."""

    @abstractmethod
    def act(self, role: str, action: dict) -> Result:
        """Validate and apply a state-changing action. Server-side only."""

    def inspect(self, role: str, query: dict) -> dict:
        """Private read-only probe, sent to one socket and never broadcast.

        This is how HANDS reads texture. Because it is not in views(), it cannot be
        recovered by scrolling back through received state in DevTools.
        """
        return {}

    def tick(self, dt: float) -> Result:
        return Result.NOTHING

    @abstractmethod
    def manual_page(self) -> str:
        """HTML for this instance's generated rules. BOOK only."""

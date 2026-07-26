
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


@dataclass
class Slot:
    """One point in a module's face. WORLD data - position only, never a property.

    See AGENTS.md hard rule 3: no colour, texture or label belongs here. If you
    want to describe what a slot *looks or feels like*, that goes in views().
    """
    idx: int
    kind: str          # "wire" | "button" | "dial" | "tile" | "vent"
    x: float           # 0..1 across the module's face
    y: float           # 0..1 down the module's face


@dataclass
class Layout:
    """A module's spatial geometry. Identical for every role - see layout()."""
    w: int              # face grid width
    h: int              # face grid height
    slots: list[Slot]


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
    def layout(self) -> Layout:
        """WORLD geometry: slot positions only. Identical for every role - see
        tests/test_layout.py. No colour, texture or label may appear here;
        that belongs in views() instead.
        """

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

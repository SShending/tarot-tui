from __future__ import annotations

import random
import secrets
from dataclasses import dataclass

from .cards import Card, TAROT_DECK


POSITIONS = ("过往", "当下", "趋势")


@dataclass(frozen=True, slots=True)
class DrawnCard:
    card: Card
    reversed: bool

    @property
    def orientation(self) -> str:
        return "逆位" if self.reversed else "正位"

    @property
    def meaning(self) -> str:
        return self.card.reversed if self.reversed else self.card.upright

    @property
    def keyword(self) -> str:
        return self.card.reversed_keyword if self.reversed else self.card.upright_keyword


@dataclass(frozen=True, slots=True)
class Reading:
    question: str
    cards: tuple[DrawnCard, DrawnCard, DrawnCard]

    def __post_init__(self) -> None:
        if len({drawn.card.name for drawn in self.cards}) != 3:
            raise ValueError("A reading must contain three distinct cards.")


def draw_reading(question: str, rng: random.Random | None = None) -> Reading:
    """Draw one auditable three-card reading without involving an interpreter."""
    source = rng or secrets.SystemRandom()
    cards = source.sample(TAROT_DECK, k=3)
    drawn = tuple(DrawnCard(card, source.random() < 0.33) for card in cards)
    return Reading(question=question.strip(), cards=drawn)  # type: ignore[arg-type]

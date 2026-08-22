from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from .cards import TAROT_DECK
from .domain import DrawnCard, Reading


OutcomeState = Literal["aligned", "partly_aligned", "different", "unresolved"]

_CARD_BY_NAME = {card.name: card for card in TAROT_DECK}
_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "career": ("工作", "职业", "事业", "实习", "面试", "offer", "公司", "项目", "创业"),
    "study": ("学习", "学业", "研究", "论文", "学校", "考试", "导师", "方向"),
    "relationship": ("感情", "关系", "恋爱", "复合", "对方", "朋友", "伴侣"),
    "decision": ("选择", "决定", "应该", "要不要", "是否", "能不能", "会不会"),
    "wellbeing": ("焦虑", "压力", "疲惫", "迷茫", "情绪", "状态"),
}


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class Reflection:
    state: OutcomeState
    note: str = ""


@dataclass(frozen=True, slots=True)
class ReadingRecord:
    id: str
    created_at: datetime
    reading: Reading
    interpretation: str
    follow_ups: tuple[ConversationTurn, ...] = ()
    reflection: Reflection | None = None

    @property
    def question(self) -> str:
        return self.reading.question


class ReadingStore(Protocol):
    def append(self, record: ReadingRecord) -> None: ...

    def list(self) -> list[ReadingRecord]: ...

    def get(self, record_id: str) -> ReadingRecord | None: ...

    def replace(self, record: ReadingRecord) -> None: ...


class JsonlReadingStore:
    """Human-inspectable local storage for tarot reading episodes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_memory_path()

    def append(self, record: ReadingRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record_to_dict(record), ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
            file.flush()
            os.fsync(file.fileno())

    def list(self) -> list[ReadingRecord]:
        if not self.path.exists():
            return []

        records: list[ReadingRecord] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    records.append(record_from_dict(payload))
                except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                    # One malformed historical row should not make the journal unusable.
                    continue
        records.sort(key=lambda record: record.created_at, reverse=True)
        return records

    def get(self, record_id: str) -> ReadingRecord | None:
        return next((record for record in self.list() if record.id == record_id), None)

    def replace(self, record: ReadingRecord) -> None:
        records = self.list()
        found = False
        updated: list[ReadingRecord] = []
        for existing in records:
            if existing.id == record.id:
                updated.append(record)
                found = True
            else:
                updated.append(existing)
        if not found:
            raise KeyError(f"Unknown reading record: {record.id}")
        self._rewrite(updated)

    def update_follow_ups(
        self,
        record_id: str,
        follow_ups: tuple[ConversationTurn, ...],
    ) -> ReadingRecord:
        record = self.get(record_id)
        if record is None:
            raise KeyError(f"Unknown reading record: {record_id}")
        updated = replace(record, follow_ups=follow_ups)
        self.replace(updated)
        return updated

    def update_reflection(self, record_id: str, reflection: Reflection) -> ReadingRecord:
        record = self.get(record_id)
        if record is None:
            raise KeyError(f"Unknown reading record: {record_id}")
        updated = replace(record, reflection=reflection)
        self.replace(updated)
        return updated

    def _rewrite(self, records: list[ReadingRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                for record in sorted(records, key=lambda item: item.created_at):
                    file.write(
                        json.dumps(
                            record_to_dict(record),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise


class MemoryRetriever:
    """Small deterministic retriever; deliberately avoids embeddings in v0.3."""

    def __init__(self, store: ReadingStore) -> None:
        self.store = store

    def retrieve(
        self,
        question: str,
        *,
        current_reading: Reading | None = None,
        limit: int = 3,
    ) -> list[ReadingRecord]:
        if limit <= 0:
            return []

        now = datetime.now(timezone.utc)
        current_cards = (
            {drawn.card.name for drawn in current_reading.cards}
            if current_reading is not None
            else set()
        )
        query_features = _text_features(question)
        query_domains = _domains(question)

        ranked: list[tuple[float, datetime, str, ReadingRecord]] = []
        for record in self.store.list():
            if current_reading is not None and record.reading == current_reading:
                continue

            record_features = _text_features(record.question)
            overlap = len(query_features & record_features)
            domains = len(query_domains & _domains(record.question))
            repeated_cards = len(
                current_cards & {drawn.card.name for drawn in record.reading.cards}
            )
            age_days = max((now - _as_utc(record.created_at)).total_seconds() / 86400, 0)
            recency = max(0.0, 1.0 - min(age_days, 365.0) / 365.0)

            score = overlap * 2.0 + domains * 4.0 + repeated_cards * 1.5 + recency
            if score <= 0:
                continue
            ranked.append((score, record.created_at, record.id, record))

        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [item[3] for item in ranked[:limit]]


def default_memory_path() -> Path:
    configured = os.environ.get("LUNAR_ARCANA_MEMORY_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".lunar-arcana" / "readings.jsonl"


def new_record(
    reading: Reading,
    interpretation: str,
    *,
    follow_ups: tuple[ConversationTurn, ...] = (),
    created_at: datetime | None = None,
) -> ReadingRecord:
    return ReadingRecord(
        id=uuid4().hex,
        created_at=created_at or datetime.now(timezone.utc),
        reading=reading,
        interpretation=interpretation,
        follow_ups=follow_ups,
    )


def record_to_dict(record: ReadingRecord) -> dict[str, object]:
    return {
        "version": 1,
        "id": record.id,
        "created_at": _as_utc(record.created_at).isoformat(),
        "question": record.question,
        "cards": [
            {"name": drawn.card.name, "reversed": drawn.reversed}
            for drawn in record.reading.cards
        ],
        "interpretation": record.interpretation,
        "follow_ups": [
            {"question": turn.question, "answer": turn.answer}
            for turn in record.follow_ups
        ],
        "reflection": (
            {"state": record.reflection.state, "note": record.reflection.note}
            if record.reflection is not None
            else None
        ),
    }


def record_from_dict(payload: object) -> ReadingRecord:
    if not isinstance(payload, dict):
        raise TypeError("Reading record must be an object")
    if payload.get("version", 1) != 1:
        raise ValueError("Unsupported reading record version")

    cards_payload = payload["cards"]
    if not isinstance(cards_payload, list) or len(cards_payload) != 3:
        raise ValueError("Reading record must contain exactly three cards")

    cards: list[DrawnCard] = []
    for item in cards_payload:
        if not isinstance(item, dict):
            raise TypeError("Card entry must be an object")
        name = str(item["name"])
        card = _CARD_BY_NAME.get(name)
        if card is None:
            raise ValueError(f"Unknown tarot card: {name}")
        reversed_value = item["reversed"]
        if not isinstance(reversed_value, bool):
            raise TypeError("Card reversed flag must be boolean")
        cards.append(DrawnCard(card=card, reversed=reversed_value))

    follow_ups_payload = payload.get("follow_ups", [])
    if not isinstance(follow_ups_payload, list):
        raise TypeError("follow_ups must be a list")
    follow_ups = tuple(
        ConversationTurn(question=str(item["question"]), answer=str(item["answer"]))
        for item in follow_ups_payload
        if isinstance(item, dict)
    )

    reflection_payload = payload.get("reflection")
    reflection: Reflection | None = None
    if reflection_payload is not None:
        if not isinstance(reflection_payload, dict):
            raise TypeError("reflection must be an object")
        state = str(reflection_payload["state"])
        if state not in {"aligned", "partly_aligned", "different", "unresolved"}:
            raise ValueError(f"Unknown reflection state: {state}")
        reflection = Reflection(  # type: ignore[arg-type]
            state=state,
            note=str(reflection_payload.get("note", "")),
        )

    created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
    reading = Reading(
        question=str(payload["question"]).strip(),
        cards=tuple(cards),  # type: ignore[arg-type]
    )
    return ReadingRecord(
        id=str(payload["id"]),
        created_at=created_at,
        reading=reading,
        interpretation=str(payload.get("interpretation", "")),
        follow_ups=follow_ups,
        reflection=reflection,
    )


def compact_memory(record: ReadingRecord) -> dict[str, object]:
    """Bounded model-facing representation of one historical episode."""

    return {
        "date": record.created_at.date().isoformat(),
        "question": record.question,
        "cards": [
            f"{drawn.card.name}（{drawn.orientation}）" for drawn in record.reading.cards
        ],
        "past_interpretation_excerpt": record.interpretation[:500],
        "reflection": (
            {"state": record.reflection.state, "note": record.reflection.note[:300]}
            if record.reflection is not None
            else None
        ),
    }


def _text_features(text: str) -> set[str]:
    normalized = "".join(character.lower() for character in text if not character.isspace())
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _domains(text: str) -> set[str]:
    lowered = text.lower()
    return {
        domain
        for domain, terms in _DOMAIN_TERMS.items()
        if any(term.lower() in lowered for term in terms)
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

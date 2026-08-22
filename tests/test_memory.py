import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tarot_tui.domain import draw_reading
from tarot_tui.memory import (
    ConversationTurn,
    JsonlReadingStore,
    MemoryRetriever,
    Reflection,
    new_record,
    record_from_dict,
    record_to_dict,
)


class MemoryPersistenceTests(unittest.TestCase):
    def test_record_round_trip_preserves_reading_and_conversation(self) -> None:
        reading = draw_reading("我是否应该继续这个研究项目？", random.Random(7))
        record = new_record(
            reading,
            "初次解读",
            follow_ups=(ConversationTurn("为什么？", "因为当前张力仍未解决。"),),
            created_at=datetime(2026, 8, 22, 6, 0, tzinfo=timezone.utc),
        )

        restored = record_from_dict(record_to_dict(record))

        self.assertEqual(record, restored)
        self.assertEqual(reading.cards, restored.reading.cards)

    def test_jsonl_store_appends_lists_and_updates_reflection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readings.jsonl"
            store = JsonlReadingStore(path)
            record = new_record(
                draw_reading("我要不要接受这份实习？", random.Random(11)),
                "先确认这份实习与你真正想学的东西是否一致。",
            )

            store.append(record)
            listed = store.list()

            self.assertEqual([record], listed)
            updated = store.update_reflection(
                record.id,
                Reflection("partly_aligned", "最后去了另一家公司，但判断标准确实变清楚了。"),
            )

            self.assertEqual(updated, store.get(record.id))
            self.assertEqual("partly_aligned", store.get(record.id).reflection.state)  # type: ignore[union-attr]

    def test_follow_up_update_rewrites_same_episode_instead_of_duplicating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            record = new_record(
                draw_reading("这个计划接下来会怎样？", random.Random(13)),
                "初次解读",
            )
            store.append(record)

            store.update_follow_ups(
                record.id,
                (ConversationTurn("趋势是什么意思？", "它描述的是条件延续。"),),
            )

            records = store.list()
            self.assertEqual(1, len(records))
            self.assertEqual(1, len(records[0].follow_ups))

    def test_malformed_rows_do_not_make_journal_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readings.jsonl"
            valid = new_record(
                draw_reading("有效记录", random.Random(17)),
                "有效解读",
            )
            path.write_text(
                "not-json\n" + json.dumps(record_to_dict(valid), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            self.assertEqual([valid], JsonlReadingStore(path).list())

    def test_replace_unknown_record_raises_without_destroying_existing_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readings.jsonl"
            store = JsonlReadingStore(path)
            record = new_record(draw_reading("原记录", random.Random(19)), "原解读")
            store.append(record)
            unknown = new_record(draw_reading("不存在", random.Random(23)), "无")

            with self.assertRaises(KeyError):
                store.replace(unknown)

            self.assertEqual([record], store.list())


class MemoryRetrievalTests(unittest.TestCase):
    def test_retriever_prefers_same_domain_and_question_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            now = datetime.now(timezone.utc)
            career = new_record(
                draw_reading("我要不要接受新的实习机会？", random.Random(29)),
                "职业解读",
                created_at=now - timedelta(days=40),
            )
            relationship = new_record(
                draw_reading("我要不要重新联系对方？", random.Random(31)),
                "关系解读",
                created_at=now - timedelta(days=2),
            )
            study = new_record(
                draw_reading("研究方向是不是应该调整？", random.Random(37)),
                "研究解读",
                created_at=now - timedelta(days=10),
            )
            for record in (career, relationship, study):
                store.append(record)

            matches = MemoryRetriever(store).retrieve(
                "我应该接受这个实习还是继续做研究？",
                limit=2,
            )

            self.assertEqual(career.id, matches[0].id)
            self.assertIn(study.id, {record.id for record in matches})
            self.assertNotIn(relationship.id, {record.id for record in matches})

    def test_retrieval_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            for seed in range(5):
                store.append(
                    new_record(
                        draw_reading(f"工作选择问题 {seed}", random.Random(seed)),
                        "解读",
                    )
                )

            matches = MemoryRetriever(store).retrieve("工作应该怎么选择？", limit=3)

            self.assertEqual(3, len(matches))


if __name__ == "__main__":
    unittest.main()

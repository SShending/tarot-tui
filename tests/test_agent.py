import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tarot_tui.agent import MemoryInterpreter
from tarot_tui.domain import draw_reading
from tarot_tui.interpretation import LocalInterpreter, OpenAIInterpreter, ReadingReport
from tarot_tui.memory import JsonlReadingStore


class FakeConversationalInterpreter:
    label = "fake"
    supports_follow_up = True

    def __init__(self) -> None:
        self.reset_count = 0

    def interpret(self, reading) -> ReadingReport:
        return ReadingReport("初次解读")

    def follow_up(self, question: str) -> ReadingReport:
        return ReadingReport(f"回应：{question}")

    def reset_conversation(self) -> None:
        self.reset_count += 1


class MemoryInterpreterTests(unittest.TestCase):
    def test_local_reading_is_persisted_without_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            interpreter = MemoryInterpreter(LocalInterpreter(), store)
            reading = draw_reading("我该怎样推进当前计划？", random.Random(5))

            report = interpreter.interpret(reading)

            self.assertFalse(report.blocked)
            records = store.list()
            self.assertEqual(1, len(records))
            self.assertEqual(reading, records[0].reading)
            self.assertEqual(report.markdown, records[0].interpretation)

    def test_follow_ups_update_same_episode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            interpreter = MemoryInterpreter(FakeConversationalInterpreter(), store)
            reading = draw_reading("这个计划接下来会怎样？", random.Random(9))

            interpreter.interpret(reading)
            interpreter.follow_up("为什么趋势不等于确定结果？")

            records = store.list()
            self.assertEqual(1, len(records))
            self.assertEqual(1, len(records[0].follow_ups))
            self.assertIn("为什么趋势", records[0].follow_ups[0].question)

    def test_storage_failure_does_not_break_reading(self) -> None:
        class BrokenStore:
            def append(self, record) -> None:
                raise OSError("disk full")

            def list(self):
                return []

            def get(self, record_id):
                return None

            def replace(self, record) -> None:
                raise OSError("disk full")

        interpreter = MemoryInterpreter(LocalInterpreter(), BrokenStore())
        reading = draw_reading("测试写入失败", random.Random(12))

        report = interpreter.interpret(reading)

        self.assertFalse(report.blocked)
        self.assertIsInstance(interpreter.last_memory_error, OSError)

    def test_retrieval_failure_does_not_downgrade_ai_reading(self) -> None:
        calls = []

        class BrokenReadStore:
            def append(self, record) -> None:
                pass

            def list(self):
                raise OSError("cannot read memory")

            def get(self, record_id):
                return None

            def replace(self, record) -> None:
                pass

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(output_text="AI 仍然完成了解读")

        base = OpenAIInterpreter(
            client=SimpleNamespace(responses=FakeResponses()),
            model="test-model",
        )
        interpreter = MemoryInterpreter(base, BrokenReadStore())
        reading = draw_reading("即使历史损坏也继续解读", random.Random(14))

        report = interpreter.interpret(reading)

        self.assertEqual("AI 仍然完成了解读", report.markdown)
        self.assertEqual(1, len(calls))
        self.assertIsInstance(interpreter.last_memory_error, OSError)

    def test_openai_reading_receives_only_bounded_relevant_history(self) -> None:
        calls = []

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(output_text="带记忆的解读")

        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            for seed, question in enumerate(
                [
                    "我要不要接受新的实习？",
                    "研究方向是不是应该调整？",
                    "工作项目应该继续吗？",
                    "感情里要不要重新联系对方？",
                ],
                start=20,
            ):
                record_reading = draw_reading(question, random.Random(seed))
                persistent = MemoryInterpreter(LocalInterpreter(), store)
                persistent.interpret(record_reading)

            base = OpenAIInterpreter(
                client=SimpleNamespace(responses=FakeResponses()),
                model="test-model",
            )
            interpreter = MemoryInterpreter(base, store)
            current = draw_reading("我应该接受这个实习还是继续做研究？", random.Random(40))

            report = interpreter.interpret(current)

            content = calls[0]["input"][0]["content"]
            self.assertIn("relevant_history", content)
            self.assertIn("past_interpretation_excerpt", content)
            self.assertLessEqual(len(interpreter.last_memories), 3)
            self.assertNotIn("感情里要不要重新联系对方", content)
            for drawn in current.cards:
                self.assertIn(drawn.card.name, content)
            self.assertIn("本次参考的历史", report.markdown)
            for memory in interpreter.last_memories:
                self.assertIn(memory.question, report.markdown)

    def test_memory_can_be_disabled_without_reading_or_writing_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            first = MemoryInterpreter(LocalInterpreter(), store)
            first.interpret(draw_reading("第一条历史", random.Random(50)))

            interpreter = MemoryInterpreter(LocalInterpreter(), store)
            interpreter.set_memory_enabled(False)
            interpreter.interpret(draw_reading("不应写入的第二条", random.Random(51)))

            records = store.list()
            self.assertEqual(1, len(records))
            self.assertEqual("第一条历史", records[0].question)
            self.assertFalse(interpreter.memory_enabled)


if __name__ == "__main__":
    unittest.main()

import random
import unittest
from types import SimpleNamespace

from tarot_tui.cards import MAJOR_ARCANA, MINOR_ARCANA, TAROT_DECK
from tarot_tui.domain import draw_reading
from tarot_tui.interpretation import (
    LocalInterpreter,
    OpenAIInterpreter,
    build_interpreter_from_env,
)


class DeckTests(unittest.TestCase):
    def test_major_arcana_is_complete_and_unique(self) -> None:
        self.assertEqual(22, len(MAJOR_ARCANA))
        self.assertEqual(22, len({card.name for card in MAJOR_ARCANA}))

    def test_full_deck_contains_78_unique_cards(self) -> None:
        self.assertEqual(56, len(MINOR_ARCANA))
        self.assertEqual(78, len(TAROT_DECK))
        self.assertEqual(78, len({card.name for card in TAROT_DECK}))
        self.assertEqual(
            {"权杖": 14, "圣杯": 14, "宝剑": 14, "星币": 14},
            {
                suit: sum(card.suit == suit for card in MINOR_ARCANA)
                for suit in ("权杖", "圣杯", "宝剑", "星币")
            },
        )

    def test_draw_contains_three_distinct_cards(self) -> None:
        reading = draw_reading("测试问题", random.Random(42))

        self.assertEqual(3, len(reading.cards))
        self.assertEqual(3, len({drawn.card.name for drawn in reading.cards}))

    def test_seeded_draw_is_reproducible(self) -> None:
        first = draw_reading("测试问题", random.Random(7))
        second = draw_reading("测试问题", random.Random(7))

        self.assertEqual(first, second)


class InterpretationTests(unittest.TestCase):
    def test_report_contains_question_cards_and_sections(self) -> None:
        reading = draw_reading("我是否应该接受新的工作机会？", random.Random(3))
        report = LocalInterpreter().interpret(reading)

        self.assertFalse(report.blocked)
        self.assertIn("直接回答", report.markdown)
        self.assertIn("牌间关系", report.markdown)
        self.assertIn("可以怎么做", report.markdown)
        for drawn in reading.cards:
            self.assertIn(drawn.card.name, report.markdown)

    def test_crisis_question_stops_divination(self) -> None:
        reading = draw_reading("我不想活了，塔罗怎么看？", random.Random(5))
        report = LocalInterpreter().interpret(reading)

        self.assertTrue(report.blocked)
        self.assertIn("先暂停占卜", report.markdown)
        self.assertNotIn("牌间关系", report.markdown)

    def test_factory_uses_local_interpreter_without_api_key(self) -> None:
        interpreter = build_interpreter_from_env({})

        self.assertIsInstance(interpreter, LocalInterpreter)

    def test_openai_interpreter_sends_question_and_fixed_cards(self) -> None:
        calls = []

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(output_text="## 直接回答\n\n这是一段针对问题的解读。")

        client = SimpleNamespace(responses=FakeResponses())
        interpreter = OpenAIInterpreter(client=client, model="test-model")
        reading = draw_reading("我八月份能获得理想的实习机会吗？", random.Random(11))

        report = interpreter.interpret(reading)

        self.assertIn("针对问题", report.markdown)
        self.assertEqual("test-model", calls[0]["model"])
        self.assertFalse(calls[0]["store"])
        self.assertIn(reading.question, calls[0]["input"])
        for drawn in reading.cards:
            self.assertIn(drawn.card.name, calls[0]["input"])
            self.assertIn(drawn.card.family, calls[0]["input"])


if __name__ == "__main__":
    unittest.main()

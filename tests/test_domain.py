import random
import unittest
from types import SimpleNamespace

from tarot_tui.cards import MAJOR_ARCANA, MINOR_ARCANA, TAROT_DECK
from tarot_tui.domain import draw_reading
from tarot_tui.interpretation import (
    LocalInterpreter,
    OpenAIInterpreter,
    build_interpreter_from_env,
    build_interpreter_from_prompt,
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

    def test_prompt_uses_local_interpreter_when_key_is_skipped(self) -> None:
        secret_prompts = []

        interpreter = build_interpreter_from_prompt(
            {},
            input_fn=lambda prompt: "",
            secret_input_fn=secret_prompts.append,
        )

        self.assertIsInstance(interpreter, LocalInterpreter)
        self.assertEqual([], secret_prompts)

    def test_prompt_passes_model_settings_to_openai_interpreter(self) -> None:
        answers = iter(["https://example.test/v1", "2", "5"])
        factory_calls = []

        class FakeModels:
            def list(self):
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(id="custom-basic"),
                        SimpleNamespace(id="custom-reasoning"),
                    ]
                )

        client = SimpleNamespace(models=FakeModels())

        def client_factory(**kwargs):
            factory_calls.append(kwargs)
            return client

        interpreter = build_interpreter_from_prompt(
            {},
            input_fn=lambda prompt: next(answers),
            secret_input_fn=lambda prompt: "test-key",
            client_factory=client_factory,
        )

        self.assertIsInstance(interpreter, OpenAIInterpreter)
        self.assertEqual("custom-reasoning", interpreter.model)
        self.assertEqual("high", interpreter.reasoning_effort)
        self.assertEqual(
            [{"api_key": "test-key", "base_url": "https://example.test/v1"}],
            factory_calls,
        )

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
        self.assertEqual({"effort": "medium"}, calls[0]["reasoning"])
        self.assertFalse(calls[0]["store"])
        initial_input = calls[0]["input"][0]["content"]
        self.assertIn(reading.question, initial_input)
        for drawn in reading.cards:
            self.assertIn(drawn.card.name, initial_input)
            self.assertIn(drawn.card.family, initial_input)

    def test_openai_interpreter_replays_full_output_for_follow_up(self) -> None:
        calls = []
        initial_output = {"type": "message", "id": "initial-output"}
        follow_up_output = {"type": "message", "id": "follow-up-output"}
        responses = iter(
            [
                SimpleNamespace(
                    output_text="## 直接回答\n\n初次解读。",
                    output=[initial_output],
                ),
                SimpleNamespace(
                    output_text="追问回应。",
                    output=[follow_up_output],
                ),
            ]
        )

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return next(responses)

        interpreter = OpenAIInterpreter(
            client=SimpleNamespace(responses=FakeResponses()),
            model="test-model",
        )
        reading = draw_reading("我该怎样推进当前计划？", random.Random(13))

        interpreter.interpret(reading)
        report = interpreter.follow_up("趋势牌为什么不是确定结果？")

        self.assertEqual("追问回应。", report.markdown)
        self.assertEqual(initial_output, calls[1]["input"][1])
        self.assertIn("趋势牌为什么不是确定结果", calls[1]["input"][2]["content"])
        self.assertFalse(calls[1]["store"])
        self.assertEqual(1100, calls[1]["max_output_tokens"])

        interpreter.reset_conversation()
        with self.assertRaisesRegex(RuntimeError, "先生成初次解读"):
            interpreter.follow_up("还能继续吗？")


if __name__ == "__main__":
    unittest.main()

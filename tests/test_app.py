import unittest

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Markdown

from tarot_tui.app import LunarArcanaApp
from tarot_tui.interpretation import LocalInterpreter, ReadingReport


class ConversationalInterpreter:
    label = "测试大模型"
    supports_follow_up = True

    def __init__(self) -> None:
        self.follow_up_questions = []
        self.reset_count = 0

    def interpret(self, reading) -> ReadingReport:
        return ReadingReport("## 直接回答\n\n这是初次解读。")

    def follow_up(self, question: str) -> ReadingReport:
        self.follow_up_questions.append(question)
        return ReadingReport("这张趋势牌描述的是条件延续，而不是确定结果。")

    def reset_conversation(self) -> None:
        self.reset_count += 1


class AppSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_shuffle_reveal_and_interpret_flow(self) -> None:
        app = LunarArcanaApp(LocalInterpreter())
        async with app.run_test(size=(100, 44)) as pilot:
            question = app.query_one("#question", Input)
            await pilot.pause()
            self.assertEqual(question.cursor_screen_offset, app.cursor_position)

            question.value = "我八月份能获得理想的实习机会吗？"
            await pilot.click("#begin")
            await pilot.pause(0.9)
            self.assertEqual(1, app.shuffle_count)
            self.assertFalse(app._shuffling)

            await pilot.click("#shuffle")
            await pilot.pause(0.9)
            self.assertEqual(2, app.shuffle_count)
            self.assertFalse(app._shuffling)

            self.assertTrue(app.query_one("#result").has_class("hidden"))
            for index in range(3):
                await pilot.click(f"#card-{index}")
                await pilot.pause(0.25)
                self.assertEqual(index + 1, app.revealed)
                if index == 0:
                    self.assertTrue(app.query_one("#shuffle").has_class("hidden"))

            self.assertTrue(app.query_one("#result").has_class("hidden"))
            interpret = app.query_one("#interpret", Button)
            self.assertFalse(interpret.has_class("hidden"))

            await pilot.click("#interpret")
            await pilot.pause(0.5)
            result = app.query_one("#result")
            self.assertFalse(result.has_class("hidden"))
            self.assertIsInstance(result, Vertical)
            self.assertNotIsInstance(result, VerticalScroll)
            self.assertFalse(app.query_one("#new-reading").has_class("hidden"))

    async def test_cards_stack_in_a_narrow_terminal(self) -> None:
        app = LunarArcanaApp(LocalInterpreter())
        async with app.run_test(size=(70, 46)) as pilot:
            await pilot.pause()
            app.query_one("#question", Input).value = "我该怎样推进当前计划？"
            await pilot.click("#begin")
            await pilot.pause(0.9)
            cards = app.query_one("#cards", Horizontal)

            self.assertTrue(cards.has_class("narrow"))
            self.assertEqual(25, cards.region.height)
            for card in cards.children:
                self.assertEqual(cards.content_region.width, card.region.width)

    async def test_model_reading_accepts_follow_up_and_clears_new_conversation(
        self,
    ) -> None:
        interpreter = ConversationalInterpreter()
        app = LunarArcanaApp(interpreter)
        async with app.run_test(size=(100, 60)) as pilot:
            app.query_one("#question", Input).value = "这个计划接下来会怎样？"
            await pilot.click("#begin")
            await pilot.pause(0.9)
            for index in range(3):
                await pilot.click(f"#card-{index}")
                await pilot.pause(0.25)

            await pilot.click("#interpret")
            await pilot.pause(0.2)
            self.assertFalse(app.query_one("#follow-up").has_class("hidden"))

            follow_up = app.query_one("#follow-up-question", Input)
            follow_up.value = "为什么趋势不等于确定结果？"
            await pilot.click("#send-follow-up")
            await pilot.pause(0.2)

            self.assertEqual(
                ["为什么趋势不等于确定结果？"],
                interpreter.follow_up_questions,
            )
            self.assertEqual("", follow_up.value)
            report = app.query_one("#report", Markdown)
            self.assertIn("为什么趋势不等于确定结果", report.source)
            self.assertIn("条件延续", report.source)

            await pilot.click("#new-reading")
            await pilot.pause()
            self.assertTrue(app.query_one("#follow-up").has_class("hidden"))
            self.assertEqual(2, interpreter.reset_count)


if __name__ == "__main__":
    unittest.main()

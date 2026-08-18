import unittest

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.geometry import Offset
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
            self.assertEqual(cards.region.y, cards.children[0].region.y)
            self.assertEqual(cards.region.bottom, cards.children[-1].region.bottom)
            for card in cards.children:
                self.assertEqual(cards.content_region.width, card.region.width)
            for previous, current in zip(cards.children, cards.children[1:]):
                self.assertEqual(previous.region.bottom + 1, current.region.y)

    async def test_report_follows_cards_without_nested_scrolling(self) -> None:
        for size in ((115, 34), (80, 32), (70, 32)):
            with self.subTest(size=size):
                app = LunarArcanaApp(LocalInterpreter())
                async with app.run_test(size=size) as pilot:
                    await pilot.pause()
                    app._start_reading("我该怎样推进当前计划？")
                    await pilot.pause(0.9)
                    for index in range(3):
                        app._reveal_card(index)
                    await pilot.pause()

                    app.interpret_pressed()
                    await pilot.pause(0.5)

                    cards = list(app.query(".tarot-card"))
                    actions = app.query_one("#actions", Horizontal)
                    result = app.query_one("#result", Vertical)
                    report = app.query_one("#report", Markdown)

                    self.assertEqual(0, actions.region.height)
                    self.assertEqual(
                        max(card.region.bottom for card in cards) + 1,
                        result.region.y,
                    )
                    self.assertGreater(app.screen.max_scroll_y, 0)
                    self.assertEqual(0, result.max_scroll_y)
                    self.assertTrue(app.screen.show_vertical_scrollbar)
                    self.assertFalse(result.show_vertical_scrollbar)

                    opening = (
                        report.children[1]
                        if len(report.children) > 1
                        else report.children[0]
                    )
                    self.assertTrue(app.screen.can_view_entire(opening))

    async def test_question_input_owns_cursor_and_keeps_layout_stable(self) -> None:
        app = LunarArcanaApp(LocalInterpreter())
        async with app.run_test(size=(80, 32)) as pilot:
            await pilot.pause()
            question = app.query_one("#question", Input)
            question_region = question.region

            self.assertTrue(question.has_focus)
            app.cursor_position = Offset(0, 0)
            app._focus_question_input()
            self.assertEqual(Offset(0, 0), app.cursor_position)

            await pilot.press("a", "中", "文")
            await pilot.pause()
            self.assertEqual("a中文", question.value)
            self.assertEqual(question_region, question.region)
            self.assertEqual(Offset(0, 0), app.screen.scroll_offset)
            self.assertEqual(question.cursor_screen_offset, app.cursor_position)

            question.value = ""
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(question.has_focus)
            self.assertEqual(question_region, question.region)
            self.assertEqual(Offset(0, 0), app.screen.scroll_offset)

            question.value = "重新占卜后仍应聚焦"
            await pilot.press("enter")
            await pilot.pause(0.9)
            app.action_new_reading()
            await pilot.pause()

            self.assertTrue(question.has_focus)
            self.assertEqual(question_region, question.region)
            self.assertEqual(Offset(0, 0), app.screen.scroll_offset)
            await pilot.press("新")
            await pilot.pause()
            self.assertEqual("新", question.value)
            self.assertEqual(question.cursor_screen_offset, app.cursor_position)

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

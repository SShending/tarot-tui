import unittest

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input

from tarot_tui.app import LunarArcanaApp
from tarot_tui.interpretation import LocalInterpreter


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


if __name__ == "__main__":
    unittest.main()

import random
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, ListView

from tarot_tui.agent import MemoryInterpreter
from tarot_tui.domain import draw_reading
from tarot_tui.interpretation import LocalInterpreter
from tarot_tui.journal import HistoryScreen, MemoryLunarArcanaApp, ReadingDetailScreen
from tarot_tui.memory import JsonlReadingStore, new_record


class JournalSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_screen_handles_empty_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            interpreter = MemoryInterpreter(LocalInterpreter(), store)
            app = MemoryLunarArcanaApp(interpreter, store)

            async with app.run_test(size=(100, 40)) as pilot:
                await pilot.press("ctrl+h")
                await pilot.pause()

                self.assertIsInstance(app.screen, HistoryScreen)
                self.assertEqual(1, len(app.screen.query("#history-empty")))

    async def test_history_can_open_record_and_save_reflection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            record = new_record(
                draw_reading("我要不要继续这个项目？", random.Random(70)),
                "这是一段历史解读。",
            )
            store.append(record)
            interpreter = MemoryInterpreter(LocalInterpreter(), store)
            app = MemoryLunarArcanaApp(interpreter, store)

            async with app.run_test(size=(100, 50)) as pilot:
                await pilot.press("ctrl+h")
                await pilot.pause()

                history = app.screen
                self.assertIsInstance(history, HistoryScreen)
                history.query_one("#history-list", ListView)

                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, ReadingDetailScreen)

                app.screen.query_one("#reflection-note", Input).value = "最后决定继续，但缩小了范围。"
                await pilot.click("#outcome-partly_aligned")
                await pilot.click("#save-reflection")
                await pilot.pause()

                updated = store.get(record.id)
                self.assertIsNotNone(updated)
                self.assertEqual("partly_aligned", updated.reflection.state)  # type: ignore[union-attr]
                self.assertIn("缩小了范围", updated.reflection.note)  # type: ignore[union-attr]

    async def test_history_screen_handles_many_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlReadingStore(Path(directory) / "readings.jsonl")
            for index in range(25):
                store.append(
                    new_record(
                        draw_reading(f"历史问题 {index}", random.Random(100 + index)),
                        f"历史解读 {index}",
                    )
                )
            interpreter = MemoryInterpreter(LocalInterpreter(), store)
            app = MemoryLunarArcanaApp(interpreter, store)

            async with app.run_test(size=(90, 32)) as pilot:
                await pilot.press("ctrl+h")
                await pilot.pause()

                history = app.screen
                self.assertIsInstance(history, HistoryScreen)
                history_list = history.query_one("#history-list", ListView)
                self.assertEqual(25, len(history_list.children))


if __name__ == "__main__":
    unittest.main()

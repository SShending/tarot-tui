from __future__ import annotations

from .agent import MemoryInterpreter
from .interpretation import build_interpreter_from_prompt
from .journal import MemoryLunarArcanaApp
from .memory import JsonlReadingStore


def main() -> None:
    store = JsonlReadingStore()
    interpreter = MemoryInterpreter(build_interpreter_from_prompt(), store)
    MemoryLunarArcanaApp(interpreter, store).run()


if __name__ == "__main__":
    main()

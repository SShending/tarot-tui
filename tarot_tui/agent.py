from __future__ import annotations

import json

from .domain import Reading
from .interpretation import (
    Interpreter,
    OpenAIInterpreter,
    ReadingReport,
    _MODEL_INSTRUCTIONS,
    _reading_input,
    _response_output,
    _response_text,
    guardrail_report,
)
from .memory import (
    ConversationTurn,
    JsonlReadingStore,
    MemoryRetriever,
    ReadingRecord,
    ReadingStore,
    compact_memory,
    new_record,
)


_MEMORY_INSTRUCTIONS = """

你还可能收到 `relevant_history`，它来自用户自己此前保存的牌局和后续反思。使用这些历史时必须遵守：
- 历史记录是上下文，不是当前牌面的额外证据；当前三张牌仍是本次塔罗解读的唯一牌面。
- 只在确实相关时引用历史，不要为了显得有记忆而强行建立联系。
- 清楚区分用户后来确认的现实事实、过去模型的解释、以及当前牌面的象征性解释。
- 如果后续反思显示过去的解读与现实不同，应明确承认差异，不得事后合理化。
- 重复出现的牌或主题不能证明命运、注定或预测能力，只能作为跨时间反思的线索。
- 不要暴露内部存储结构、record id 或检索分数。
""".rstrip()


class MemoryInterpreter:
    """Persist readings and add a bounded amount of relevant history to AI readings."""

    def __init__(
        self,
        interpreter: Interpreter,
        store: ReadingStore | None = None,
        *,
        memory_enabled: bool = True,
    ) -> None:
        self.interpreter = interpreter
        self.store = store or JsonlReadingStore()
        self.retriever = MemoryRetriever(self.store)
        self.memory_enabled = memory_enabled
        self._current_record_id: str | None = None
        self._follow_ups: list[ConversationTurn] = []
        self.last_memories: tuple[ReadingRecord, ...] = ()
        self.last_memory_error: Exception | None = None

    @property
    def label(self) -> str:
        suffix = " · memory" if self.memory_enabled else ""
        return f"{self.interpreter.label}{suffix}"

    @property
    def supports_follow_up(self) -> bool:
        return self.interpreter.supports_follow_up

    def interpret(self, reading: Reading) -> ReadingReport:
        self._current_record_id = None
        self._follow_ups.clear()
        self.last_memories = ()
        self.last_memory_error = None

        if self.memory_enabled and isinstance(self.interpreter, OpenAIInterpreter):
            memories = tuple(
                self.retriever.retrieve(reading.question, current_reading=reading, limit=3)
            )
            self.last_memories = memories
            report = self._interpret_openai(reading, memories)
            if memories and not report.blocked:
                report = ReadingReport(
                    report.markdown + _memory_reference_markdown(memories),
                    blocked=False,
                )
        else:
            report = self.interpreter.interpret(reading)

        if not report.blocked:
            self._persist_new_record(reading, report.markdown)
        return report

    def follow_up(self, question: str) -> ReadingReport:
        report = self.interpreter.follow_up(question)
        if report.blocked:
            return report

        self._follow_ups.append(
            ConversationTurn(question=question.strip(), answer=report.markdown)
        )
        self._persist_follow_ups()
        return report

    def reset_conversation(self) -> None:
        self._current_record_id = None
        self._follow_ups.clear()
        self.last_memories = ()
        self.interpreter.reset_conversation()

    def set_memory_enabled(self, enabled: bool) -> None:
        self.memory_enabled = enabled

    def _interpret_openai(
        self,
        reading: Reading,
        memories: tuple[ReadingRecord, ...],
    ) -> ReadingReport:
        interpreter = self.interpreter
        assert isinstance(interpreter, OpenAIInterpreter)

        interpreter.reset_conversation()
        generation = interpreter._conversation_generation
        guardrail = guardrail_report(reading.question)
        if guardrail:
            return guardrail

        content = _reading_input(reading)
        if memories:
            history_payload = [compact_memory(record) for record in memories]
            content += (
                "\n\n以下 JSON 是与当前问题最相关的历史牌局摘要。"
                "它们只能作为用户历史上下文，不能覆盖当前固定牌面：\n"
                + json.dumps(
                    {"relevant_history": history_payload},
                    ensure_ascii=False,
                    indent=2,
                )
            )

        user_item = {"role": "user", "content": content}
        response = interpreter._create_response(
            input_items=[user_item],
            instructions=_MODEL_INSTRUCTIONS + _MEMORY_INSTRUCTIONS,
            max_output_tokens=1900,
        )
        text = _response_text(response)
        if generation != interpreter._conversation_generation:
            raise RuntimeError("当前牌局已经结束")
        interpreter._conversation = [user_item, *_response_output(response, text)]
        return ReadingReport(text)

    def _persist_new_record(self, reading: Reading, interpretation: str) -> None:
        try:
            record = new_record(reading, interpretation)
            self.store.append(record)
            self._current_record_id = record.id
        except Exception as error:
            # Memory is additive. A storage failure must never break a reading.
            self.last_memory_error = error
            self._current_record_id = None

    def _persist_follow_ups(self) -> None:
        if self._current_record_id is None:
            return
        updater = getattr(self.store, "update_follow_ups", None)
        if updater is None:
            return
        try:
            updater(self._current_record_id, tuple(self._follow_ups))
        except Exception as error:
            self.last_memory_error = error


def _memory_reference_markdown(memories: tuple[ReadingRecord, ...]) -> str:
    lines = ["\n\n---\n\n### 本次参考的历史"]
    for record in memories:
        lines.append(f"- {record.created_at.date().isoformat()} · {record.question}")
    lines.append("\n这些历史只作为上下文，不增加本次牌面的确定性。")
    return "\n".join(lines)


def memory_interpreter(
    interpreter: Interpreter,
    store: ReadingStore | None = None,
) -> MemoryInterpreter:
    return MemoryInterpreter(interpreter, store)
